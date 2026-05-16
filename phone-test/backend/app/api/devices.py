from __future__ import annotations

import asyncio
import logging
from typing import List, Any
import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import verify_token
from app.config import get_settings
from app.models.device import Device, DeviceStatus
from app.schemas import DeviceOut, MessageOut, VisionRequest
from app.services.device_manager import device_manager
from app.services.screenshot import capture_screenshot, ScreenshotError, check_camera
from app.services.coordinate import CoordinateMapper
from app.services.motion import MotionController
from app.services.moonraker_client import _get_shared_session, MoonrakerClient, DeviceConnectionError
from app.services.ssh_tool import get_ssh_tool, SSHConnectionError, SSHAuthError, SSHCommandNotAllowedError
from app.vision.manager import vision_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

SCAN_CONCURRENCY = 15  # 扫描时最多15个并发探测


async def _get_or_create_client(device_id: int, db: AsyncSession) -> MoonrakerClient:
    """获取已有 MoonrakerClient 或从数据库重建"""
    client = device_manager.get_client(device_id)
    if client:
        return client
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, f"Device {device_id} not found")
    settings = get_settings()
    client = MoonrakerClient(dev.ip, settings.device_moonraker_port)
    device_manager._clients[device_id] = client
    return client


async def _probe_moonraker(ip: str, port: int, timeout: float = 2.0, *,
                           semaphore: asyncio.Semaphore | None = None) -> bool:
    """尝试连接 Moonraker HTTP，有响应即返回 True（用共享session）"""
    async def _do():
        try:
            session = await _get_shared_session()
            async with session.get(
                f"http://{ip}:{port}/server/info",
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as r:
                return r.status < 500
        except Exception:
            return False
    if semaphore:
        async with semaphore:
            return await _do()
    return await _do()


@router.post("/scan", response_model=List[DeviceOut])
async def scan_devices(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    """并发探测局域网 IP 范围，只对在线/已知设备入库，避免创建大量幽灵记录"""
    settings = get_settings()
    prefix = ".".join(settings.device_ip_start.split(".")[:-1])
    start = int(settings.device_ip_start.split(".")[-1])
    end = int(settings.device_ip_end.split(".")[-1])
    port = settings.device_moonraker_port

    # 并发探测所有 IP（限制并发数避免连接风暴）
    ips = [f"{prefix}.{i}" for i in range(start, end + 1)]
    sem = asyncio.Semaphore(SCAN_CONCURRENCY)
    results = await asyncio.gather(*[_probe_moonraker(ip, port, semaphore=sem) for ip in ips])
    online_ips = {ip for ip, ok in zip(ips, results) if ok}
    logger.info("Scan done: %d/%d online", len(online_ips), len(ips))

    # 同步到数据库：更新已有设备状态 + 只为在线新设备入库
    result = await db.execute(select(Device))
    existing = {d.ip: d for d in result.scalars().all()}

    for idx, ip in enumerate(ips, 1):
        online = ip in online_ips
        if ip in existing:
            existing[ip].status = DeviceStatus.ONLINE if online else DeviceStatus.OFFLINE
        elif online:
            # 只把在线设备入库，不创建离线幽灵设备
            hostname = f"nb-{idx:02d}"
            db.add(Device(ip=ip, hostname=hostname, status=DeviceStatus.ONLINE))

    await db.commit()

    # 为新入库设备创建 MoonrakerClient
    result = await db.execute(select(Device).order_by(Device.id))
    devices = result.scalars().all()
    for dev in devices:
        if dev.id not in device_manager._clients:
            device_manager._clients[dev.id] = MoonrakerClient(
                dev.ip, settings.device_moonraker_port
            )
    return devices


class DeviceCreateRequest(BaseModel):
    ip: str
    hostname: str = ""


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    req: DeviceCreateRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(select(Device).where(Device.ip == req.ip))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Device with IP {req.ip} already exists (id={existing.id})")
    hostname = req.hostname or f"n{req.ip.split('.')[-1]}"
    dev = Device(ip=req.ip, hostname=hostname, status=DeviceStatus.OFFLINE)
    db.add(dev)
    await db.commit()
    await db.refresh(dev)
    settings = get_settings()
    device_manager._clients[dev.id] = MoonrakerClient(dev.ip, settings.device_moonraker_port)
    online = await _probe_moonraker(dev.ip, settings.device_moonraker_port)
    if online:
        dev.status = DeviceStatus.ONLINE
        await db.commit()
        await db.refresh(dev)
    logger.info("Device created manually: id=%d ip=%s hostname=%s online=%s", dev.id, dev.ip, dev.hostname, online)
    return dev


@router.delete("/{device_id}", response_model=MessageOut)
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")
    await db.delete(dev)
    await db.commit()
    device_manager._clients.pop(device_id, None)
    logger.info("Device deleted: id=%d ip=%s", device_id, dev.ip)
    return {"message": f"Device {device_id} ({dev.ip}) deleted"}


@router.get("", response_model=List[DeviceOut])
async def list_devices(db: AsyncSession = Depends(get_db), _=Depends(verify_token)):
    result = await db.execute(select(Device).order_by(Device.id))
    return result.scalars().all()


@router.get("/{device_id}/status", response_model=DeviceOut)
async def get_device_status(
    device_id: int, db: AsyncSession = Depends(get_db), _=Depends(verify_token)
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")
    return dev


@router.post("/{device_id}/reset", response_model=MessageOut)
async def reset_device(device_id: int, _=Depends(verify_token)):
    await device_manager.reset_device(device_id)
    return {"message": f"Device {device_id} reset from ESTOP"}


@router.post("/{device_id}/home", response_model=MessageOut)
async def home_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    client = await _get_or_create_client(device_id, db)
    last_error = None
    for attempt in range(1, 4):
        try:
            await client.ensure_ready(max_wait=25.0)
            await client.home()
            return {"message": f"Device {device_id} homing (G28) sent (attempt {attempt})"}
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            logger.warning(
                "G28 attempt %d failed on device %d: %s", attempt, device_id, e
            )
            if "shutdown" in err_str or "tmcuart" in err_str or "homing" in err_str:
                await asyncio.sleep(2)
                continue
            else:
                break
    raise HTTPException(502, f"G28 failed after {attempt} attempts: {last_error}")


@router.post("/{device_id}/firmware_restart", response_model=MessageOut)
async def firmware_restart_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    client = await _get_or_create_client(device_id, db)
    await client.firmware_restart()
    return {"message": f"Device {device_id} firmware restarting"}


@router.post("/{device_id}/park_y", response_model=MessageOut)
async def park_y_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """Y轴归位到0，让摄像头避开手机屏幕上方，以便拍摄清晰画面"""
    client = await _get_or_create_client(device_id, db)
    motion = MotionController(client)
    try:
        await client.ensure_ready()
        await motion.park_y()
    except Exception as e:
        raise HTTPException(502, f"Park Y failed: {e}")
    return {"message": f"Device {device_id} Y-axis parked"}


@router.post("/{device_id}/vision")
async def vision_action(
    device_id: int,
    req: VisionRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
) -> Any:
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")
    try:
        screenshot = await capture_screenshot(dev.ip)
    except ScreenshotError as e:
        raise HTTPException(502, str(e))

    try:
        if req.method == "find_icon":
            template_name = req.params.get("template", req.params.get("icon", ""))
            if not template_name:
                raise HTTPException(400, "params.template is required")
            app_name = req.params.get("app", "_common")
            threshold = float(req.params.get("threshold", 0.85))
            match = await vision_manager.find_icon(screenshot, template_name, app_name=app_name, threshold=threshold)
            if match:
                return {"method": "find_icon", "template": template_name, "result": {"x": match.x, "y": match.y, "w": match.w, "h": match.h, "confidence": match.confidence}}
            return {"method": "find_icon", "template": template_name, "result": None}

        elif req.method == "read_text":
            region = req.params.get("region")
            texts = await vision_manager.read_text(screenshot, region)
            return {"method": "read_text", "result": [{"text": t.text, "x": t.x, "y": t.y, "w": t.w, "h": t.h, "confidence": t.confidence} for t in texts]}

        elif req.method == "detect_anomaly":
            anomaly = await vision_manager.detect_anomaly(screenshot)
            return {"method": "detect_anomaly", "result": anomaly}

        elif req.method == "detect_targets":
            app_name = req.params.get("app", "_common")
            targets = await vision_manager.detect_targets(screenshot, app_name=app_name)
            return {
                "method": "detect_targets",
                "result": [
                    {
                        "label": t.label,
                        "x": t.x,
                        "y": t.y,
                        "w": t.w,
                        "h": t.h,
                        "kind": t.kind,
                        "confidence": t.confidence,
                    }
                    for t in targets
                ],
            }

        else:
            raise HTTPException(400, f"Unknown vision method: {req.method}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("vision_action failed: method=%s", req.method)
        raise HTTPException(500, f"Vision inference failed: {type(e).__name__}: {e}")


@router.get("/{device_id}/position")
async def get_device_position(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """读取机械臂当前 XY 位置（mm），用于手眼标定"""
    client = await _get_or_create_client(device_id, db)
    try:
        await client.ensure_ready()
        status = await client.get_printer_status()
        pos = (
            status.get("result", {})
            .get("status", {})
            .get("gcode_move", {})
            .get("gcode_position", None)
        )
        if pos is None:
            pos = (
                status.get("result", {})
                .get("status", {})
                .get("toolhead", {})
                .get("position", [0, 0, 0, 0])
            )
        return {"x": round(pos[0], 3), "y": round(pos[1], 3), "z": round(pos[2], 3)}
    except DeviceConnectionError as e:
        raise HTTPException(502, f"Device not ready: {e}")
    except Exception as e:
        raise HTTPException(502, f"Failed to read position: {e}")


class MoveToPixelRequest(BaseModel):
    px: float  # 像素坐标 X (0~720)
    py: float  # 像素坐标 Y (0~1280)


@router.post("/{device_id}/move_to_pixel")
async def move_to_pixel(
    device_id: int,
    req: MoveToPixelRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """像素坐标 → 标定转换 → 机械臂移动（用于验证标定精度）"""
    # 获取设备
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    # 获取标定数据
    from app.models.calibration import CalibrationData
    cal_result = await db.execute(
        select(CalibrationData).where(CalibrationData.device_id == device_id)
    )
    cal = cal_result.scalar_one_or_none()

    mapper = CoordinateMapper(cal)
    try:
        mx, my = mapper.pixel_to_mech(req.px, req.py)
    except ValueError as e:
        raise HTTPException(400, f"坐标转换失败: {e}")

    # 确保 Moonraker 客户端可用
    client = await _get_or_create_client(device_id, db)

    # 移动机械臂（安全动作：先升Z再走XY）
    move_error: str | None = None
    motion = MotionController(client)
    try:
        await client.ensure_ready()
        await motion.move_to(mx, my)
    except Exception as e:
        move_error = str(e)
        logger.warning("move_to_pixel failed: device=%d err=%s", device_id, e)

    calibrated = cal is not None
    logger.info(
        "move_to_pixel: device=%d pixel=(%.0f,%.0f) → mech=(%.2f,%.2f) calibrated=%s moved=%s",
        device_id, req.px, req.py, mx, my, calibrated, move_error is None,
    )
    msg = f"pixel({req.px:.0f},{req.py:.0f}) → mech({mx:.2f},{my:.2f})mm"
    if not calibrated:
        msg += " [未标定]"
    return {
        "pixel": {"x": req.px, "y": req.py},
        "mech": {"x": mx, "y": my},
        "calibrated": calibrated,
        "moved": move_error is None,
        "move_error": move_error,
        "message": msg,
    }


@router.post("/{device_id}/tap_pixel")
async def tap_pixel(
    device_id: int,
    req: MoveToPixelRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """像素坐标 → 标定转换 → 机械臂点击（XY移动 + Z轴下压抬起）"""
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    from app.models.calibration import CalibrationData
    cal_result = await db.execute(
        select(CalibrationData).where(CalibrationData.device_id == device_id)
    )
    cal = cal_result.scalar_one_or_none()

    mapper = CoordinateMapper(cal)
    try:
        mx, my = mapper.pixel_to_mech(req.px, req.py)
    except ValueError as e:
        raise HTTPException(400, f"坐标转换失败: {e}")

    client = await _get_or_create_client(device_id, db)

    tap_error: str | None = None
    motion = MotionController(client)
    try:
        await client.ensure_ready()
        await motion.tap(mx, my)
    except Exception as e:
        tap_error = str(e)
        logger.warning("tap_pixel failed: device=%d err=%s", device_id, e)

    calibrated = cal is not None
    logger.info(
        "tap_pixel: device=%d pixel=(%.0f,%.0f) → mech=(%.2f,%.2f) calibrated=%s tapped=%s",
        device_id, req.px, req.py, mx, my, calibrated, tap_error is None,
    )
    msg = f"pixel({req.px:.0f},{req.py:.0f}) → mech({mx:.2f},{my:.2f})mm"
    if not calibrated:
        msg += " [未标定]"
    return {
        "pixel": {"x": req.px, "y": req.py},
        "mech": {"x": mx, "y": my},
        "calibrated": calibrated,
        "tapped": tap_error is None,
        "tap_error": tap_error,
        "message": msg,
    }


@router.get("/{device_id}/snapshot")
async def snapshot_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """按需从 N1 拍一张照片并返回，无视频流"""
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")
    try:
        data = await capture_screenshot(dev.ip)
        from fastapi.responses import Response
        return Response(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"})
    except ScreenshotError as e:
        raise HTTPException(502, str(e))


@router.get("/{device_id}/diagnose")
async def diagnose_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    """诊断设备连通性：Moonraker心跳 + go2rtc摄像头状态"""
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    settings = get_settings()
    diag = {"device_id": device_id, "ip": dev.ip, "status": dev.status.value}

    # Moonraker心跳
    client = device_manager.get_client(device_id)
    if not client:
        client = MoonrakerClient(dev.ip, settings.device_moonraker_port)
    diag["moonraker"] = {"reachable": False}
    try:
        alive = await client.is_alive()
        diag["moonraker"]["reachable"] = alive
        if alive:
            info = await client._request("GET", "/server/info")
            diag["moonraker"]["klippy_connected"] = info.get("result", {}).get("klippy_connected", False)
    except Exception as e:
        diag["moonraker"]["error"] = str(e)

    # go2rtc摄像头
    diag["camera"] = await check_camera(dev.ip)

    return diag


@router.get("/{device_id}/diagnose_ssh")
async def diagnose_ssh(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    ssh = get_ssh_tool()
    try:
        report = await ssh.diagnose(dev.ip)
    except SSHAuthError as e:
        raise HTTPException(401, f"SSH auth failed: {e}")
    except SSHConnectionError as e:
        raise HTTPException(504, f"SSH connection failed: {e}")

    return {
        "device_id": device_id,
        "ip": dev.ip,
        "klippy_state": report.klippy_state,
        "klippy_process_running": report.klippy_process_running,
        "moonraker_process_running": report.moonraker_process_running,
        "mcu_serial_devices": report.mcu_serial_devices,
        "klippy_log": report.klippy_log[:2000],
        "moonraker_log": report.moonraker_log[:1000],
        "errors": report.errors,
    }


class SSHRepairRequest(BaseModel):
    action: str


@router.post("/{device_id}/repair_ssh")
async def repair_ssh(
    device_id: int,
    req: SSHRepairRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    service_map = {
        "restart_klipper": "klipper",
        "restart_moonraker": "moonraker",
    }
    service = service_map.get(req.action)
    if not service:
        raise HTTPException(400, f"Invalid action: {req.action}. Valid: restart_klipper, restart_moonraker")

    ssh = get_ssh_tool()
    try:
        success = await ssh.restart_service(dev.ip, service)
    except SSHAuthError as e:
        raise HTTPException(401, f"SSH auth failed: {e}")
    except SSHConnectionError as e:
        raise HTTPException(504, f"SSH connection failed: {e}")
    except SSHCommandNotAllowedError as e:
        raise HTTPException(400, str(e))

    klippy_state_after = None
    if success:
        client = device_manager.get_client(device_id)
        if client:
            await asyncio.sleep(3)
            klippy_state_after = await client.get_klippy_state()

    return {
        "device_id": device_id,
        "action": req.action,
        "success": success,
        "klippy_state_after": klippy_state_after,
    }


@router.post("/{device_id}/preflight")
async def preflight_check(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(404, "Device not found")

    settings = get_settings()
    moonraker_result = {"reachable": False, "klippy_state": None}
    client = device_manager.get_client(device_id)
    if not client:
        client = MoonrakerClient(dev.ip, settings.device_moonraker_port)

    moonraker_result["reachable"] = await client.is_alive()
    if moonraker_result["reachable"]:
        moonraker_result["klippy_state"] = await client.get_klippy_state()

    ssh = get_ssh_tool()
    ssh_passed = False
    ssh_message = ""
    try:
        ssh_passed, ssh_message = await ssh.preflight_check(dev.ip)
    except SSHAuthError as e:
        ssh_message = f"SSH auth failed: {e}"
    except SSHConnectionError as e:
        ssh_message = f"SSH connection failed: {e}"

    all_passed = (
        moonraker_result["reachable"]
        and moonraker_result.get("klippy_state") == "ready"
        and ssh_passed
    )

    return {
        "device_id": device_id,
        "ip": dev.ip,
        "moonraker": moonraker_result,
        "ssh_preflight": {"passed": ssh_passed, "message": ssh_message},
        "all_passed": all_passed,
    }
