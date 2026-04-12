import asyncio
import logging
import yaml
from datetime import datetime, timezone

from app.services.moonraker_client import MoonrakerClient
from app.services.motion import MotionController
from app.services.screenshot import capture_screenshot
from app.services.coordinate import CoordinateMapper
from app.vision.manager import vision_manager
from app.ws_manager import ws_manager

logger = logging.getLogger(__name__)


class FlowEngine:
    def __init__(
        self,
        device_id: int,
        device_ip: str,
        client: MoonrakerClient,
        coord_mapper: CoordinateMapper,
    ):
        self.device_id = device_id
        self.device_ip = device_ip
        self.motion = MotionController(client)
        self.coord = coord_mapper
        self._stopped = False
        self._app_name = ""  # set from YAML template

    def stop(self):
        self._stopped = True

    async def execute_yaml(self, yaml_content: str) -> dict:
        template = yaml.safe_load(yaml_content)
        steps = template.get("steps", [])
        self._app_name = template.get("app", template.get("app_name", ""))
        total = len(steps)
        results = {"success": 0, "failed": 0, "stopped": False, "errors": []}

        for i, step in enumerate(steps):
            if self._stopped:
                results["stopped"] = True
                break

            action = step.get("action", "")
            await ws_manager.broadcast("task_progress", {
                "device_id": self.device_id,
                "step": i + 1,
                "total": total,
                "action": action,
            })

            try:
                await self._execute_step(step)
                results["success"] += 1
                logger.info("[%d] Step %d/%d OK: %s", self.device_id, i + 1, total, action)
            except Exception as e:
                results["failed"] += 1
                error_msg = f"Step {i+1} ({action}): {e}"
                results["errors"].append(error_msg)
                logger.error("[%d] %s", self.device_id, error_msg)
                # Safety: raise Z on failure
                try:
                    await self.motion.client.send_gcode("G1 Z30 F3000")
                except Exception:
                    pass

        return results

    async def _execute_step(self, step: dict):
        action = step["action"]
        wait = step.get("wait", 0)

        if action == "tap_icon":
            template_name = step.get("template", step.get("icon", step.get("target", "")))
            threshold = step.get("threshold", 0.85)
            await self._tap_icon(template_name, threshold)
        elif action == "tap":
            await self._tap_percent(step.get("screen_percent", [50, 50]))
        elif action == "detect_state":
            templates = step.get("templates", [])
            ocr_keywords = step.get("ocr_keywords", [])
            # Backwards compat: if 'expected'/'expect' string provided, use as OCR keyword
            expected = step.get("expected", step.get("expect", ""))
            if expected and not ocr_keywords:
                ocr_keywords = [kw.strip() for kw in expected.split("，") if kw.strip()]
                if not ocr_keywords:
                    ocr_keywords = [expected]
            timeout = step.get("timeout", 5)
            await self._detect_state(templates, ocr_keywords, timeout)
        elif action == "verify_action":
            pass
        elif action == "detect_anomaly":
            await self._detect_anomaly()
        elif action in ("swipe_up", "swipe_down", "swipe_left", "swipe_right", "swipe"):
            await self._swipe(action, step)
        elif action == "long_press":
            px, py = step.get("screen_percent", [50, 50])
            mx, my = self.coord.pixel_to_mech(px * 12.8, py * 7.2)
            await self.motion.long_press(mx, my, step.get("seconds", 1))
        elif action == "wait":
            await asyncio.sleep(step.get("seconds", 1))
        else:
            logger.warning("Unknown action: %s", action)

        # Handle wait as number or [min, max] for random
        if isinstance(wait, list) and len(wait) == 2:
            import random
            await asyncio.sleep(random.uniform(wait[0], wait[1]))
        elif wait > 0:
            await asyncio.sleep(wait)

    async def _tap_icon(self, template_name: str, threshold: float = 0.85):
        screenshot = await capture_screenshot(self.device_ip)
        coords = await vision_manager.find_icon(
            screenshot, template_name, app_name=self._app_name, threshold=threshold,
        )
        if coords is None:
            # Fallback: try OCR to find the text
            text_coords = await vision_manager.read_text(screenshot)
            for t in text_coords:
                if template_name in t.text:
                    coords = (t.x, t.y)
                    logger.info("tap_icon OCR fallback: '%s' found via text at (%.0f, %.0f)",
                                template_name, t.x, t.y)
                    break
        if coords is None:
            raise RuntimeError(f"Template '{template_name}' not found (app={self._app_name})")
        px, py = coords
        mx, my = self.coord.pixel_to_mech(px, py)
        await self.motion.tap(mx, my)

    async def _tap_percent(self, percent: list):
        px = percent[0] / 100 * 1280
        py = percent[1] / 100 * 720
        mx, my = self.coord.pixel_to_mech(px, py)
        await self.motion.tap(mx, my)

    async def _detect_state(
        self,
        templates: list[str],
        ocr_keywords: list[str],
        timeout_s: int,
    ):
        for _ in range(timeout_s * 2):  # Check every 0.5s
            screenshot = await capture_screenshot(self.device_ip)
            if await vision_manager.detect_page_state(
                screenshot,
                templates=templates or None,
                ocr_keywords=ocr_keywords or None,
                app_name=self._app_name,
            ):
                return
            await asyncio.sleep(0.5)
        desc = f"templates={templates}, keywords={ocr_keywords}"
        raise RuntimeError(f"Page state not detected within {timeout_s}s ({desc})")

    async def _detect_anomaly(self):
        screenshot = await capture_screenshot(self.device_ip)
        anomaly = await vision_manager.detect_anomaly(screenshot, app_name=self._app_name)
        if anomaly:
            logger.warning("[%d] Anomaly detected: %s", self.device_id, anomaly)
            await ws_manager.broadcast("anomaly", {
                "device_id": self.device_id, "description": anomaly,
            })

    async def _swipe(self, action: str, step: dict):
        # Support 'swipe' with direction field
        if action == "swipe":
            direction = step.get("direction", "up")
            action = f"swipe_{direction}"

        start = step.get("start_percent", [50, 80])
        end = step.get("end_percent", [50, 20])

        if action == "swipe_up" and "start_percent" not in step:
            start, end = [50, 80], [50, 20]
        elif action == "swipe_down" and "start_percent" not in step:
            start, end = [50, 20], [50, 80]
        elif action == "swipe_left" and "start_percent" not in step:
            start, end = [80, 50], [20, 50]
        elif action == "swipe_right" and "start_percent" not in step:
            start, end = [20, 50], [80, 50]

        x1 = start[0] / 100 * 1280
        y1 = start[1] / 100 * 720
        x2 = end[0] / 100 * 1280
        y2 = end[1] / 100 * 720

        mx1, my1 = self.coord.pixel_to_mech(x1, y1)
        mx2, my2 = self.coord.pixel_to_mech(x2, y2)
        duration = step.get("duration_ms", step.get("duration", 500))
        if isinstance(duration, float) and duration < 10:
            duration = int(duration * 1000)  # convert seconds to ms

        repeat = step.get("repeat", 1)
        wait = step.get("wait", 0)

        for i in range(repeat):
            await self.motion.swipe(mx1, my1, mx2, my2, duration)
            if i < repeat - 1 and wait:
                if isinstance(wait, list) and len(wait) == 2:
                    import random
                    await asyncio.sleep(random.uniform(wait[0], wait[1]))
                elif isinstance(wait, (int, float)) and wait > 0:
                    await asyncio.sleep(wait)
