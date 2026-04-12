import asyncio
import logging
import aiohttp
from io import BytesIO
from PIL import Image
from app.config import get_settings
from app.services.moonraker_client import _get_shared_session

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
MAX_RETRIES = 3          # go2rtc 首次取帧可能 502，多重试几次
RETRY_DELAY = 0.8        # 502 时等待后重试
EXPECTED_WIDTH = 1280
EXPECTED_HEIGHT = 720


class ScreenshotError(Exception):
    pass


async def capture_screenshot(device_ip: str) -> bytes:
    settings = get_settings()
    # go2rtc 按需取帧接口（官方标准）
    url = f"http://{device_ip}:{settings.device_camera_port}/api/frame.jpeg?src=camera0"

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            session = await _get_shared_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)) as resp:
                if resp.status == 502:
                    # go2rtc 流未就绪，稍等后重试
                    logger.warning(
                        "Screenshot %s attempt %d/%d: 502 (stream not ready), retrying...",
                        device_ip, attempt, MAX_RETRIES,
                    )
                    last_error = ScreenshotError(f"go2rtc {device_ip} 502")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)
                    continue
                if resp.status != 200:
                    raise ScreenshotError(
                        f"go2rtc {device_ip} returned {resp.status}"
                    )
                content_type = resp.headers.get("Content-Type", "")
                if "image" not in content_type:
                    raise ScreenshotError(
                        f"Unexpected Content-Type: {content_type}"
                    )
                data = await resp.read()
        except ScreenshotError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as e:
            logger.warning(
                "Screenshot %s attempt %d/%d failed: %s",
                device_ip, attempt, MAX_RETRIES, e,
            )
            last_error = e
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            continue

        # 解码验证并旋转 90° 顺时针（摄像头横装，手机竖向）
        try:
            img = Image.open(BytesIO(data))
            w, h = img.size
            if w == EXPECTED_WIDTH and h == EXPECTED_HEIGHT:
                img = img.rotate(-90, expand=True)   # 顺时针 90°（摄像头横装，手机竖向）
            else:
                logger.warning("Screenshot %s unexpected size: %dx%d", device_ip, w, h)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
        except Exception as e:
            raise ScreenshotError(f"Invalid image from {device_ip}: {e}") from e

        logger.info("[%s] Screenshot captured, %d bytes", device_ip, len(data))
        return data

    raise ScreenshotError(
        f"go2rtc {device_ip} failed after {MAX_RETRIES} retries"
    ) from last_error
