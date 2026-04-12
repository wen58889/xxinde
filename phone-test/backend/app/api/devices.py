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
from app.services.screenshot import capture_screenshot, ScreenshotError
from app.services.coordinate import CoordinateMapper
from app.services.motion import MotionController
from app.services.moonraker_client import _get_shared_session, MoonrakerClient
from app.vision.manager import vision_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

SCAN_CONCURRENCY = 15  # 扫描时最多15个并发探测


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
    client = device_manager.get_client(device_id)
    if not client:
        # 客户端未初始化，从数据库读取 IP 直接创建临时客户端
        result = await db.execute(select(Device).where(Device.id == device_id))
        dev = result.scalar_one_or_none()
        if not dev:
            raise HTTPException(404, f"Device {device_id} not found")
        settings = get_settings()
        from app.services.moonraker_client import MoonrakerClient as _MC, DeviceConnectionError
        client = _MC(dev.ip, settings.device_moonraker_port)
        device_manager._clients[device_id] = client  # register for future use
    try:
        await client.home()
    except Exception as e:
        raise HTTPException(502, f"G28 failed: {e}")
    return {"message": f"Device {device_id} homing (G28) sent"}


@router.post("/{device_id}/firmware_restart", response_model=MessageOut)
async def firmware_restart_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(verify_token),
):
    client = device_manager.get_client(device_id)
    if not client:
        result = await db.execute(select(Device).where(Device.id == device_id))
        dev = result.scalar_one_or_none()
        if not dev:
            raise HTTPException(404, f"Device {device_id} not found")
        settings = get_settings()
        from app.services.moonraker_client import MoonrakerClient as _MC
        client = _MC(dev.ip, settings.device_moonraker_port)
        device_manager._clients[device_id] = client
    await client.firmware_restart()
    return {"message": f"Device {device_id} firmware restarting"}


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
    client = device_manager.get_client(device_id)
    if not client:
        result = await db.execute(select(Device).where(Device.id == device_id))
        dev = result.scalar_one_or_none()
        if not dev:
            raise HTTPException(404, f"Device {device_id} not found")
        settings = get_settings()
        from app.services.moonraker_client import MoonrakerClient as _MC
        client = _MC(dev.ip, settings.device_moonraker_port)
        device_manager._clients[device_id] = client
    try:
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
    client = device_manager.get_client(device_id)
    if not client:
        settings = get_settings()
        from app.services.moonraker_client import MoonrakerClient as _MC
        client = _MC(dev.ip, settings.device_moonraker_port)
        device_manager._clients[device_id] = client

    # 移动机械臂（安全动作：先升Z再走XY）
    move_error: str | None = None
    motion = MotionController(client)
    try:
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
