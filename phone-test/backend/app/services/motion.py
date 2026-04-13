from __future__ import annotations

import logging
from app.services.moonraker_client import MoonrakerClient, DeviceConnectionError

logger = logging.getLogger(__name__)

# Limits from spec
X_MIN, X_MAX = 0.0, 150.0
Y_MIN, Y_MAX = 0.0, 150.0
Z_MIN, Z_MAX = -0.2, 2.0
Z_SAFE = 1.5       # Safe Z height for XY travel (must be < Z_MAX)
XY_MAX_FEED = 9000  # F9000 = 150mm/s
Z_MAX_FEED = 4800   # F4800 = 80mm/s
TAP_Z = 0.0         # Touch height
DEFAULT_XY_FEED = 6000
DEFAULT_Z_FEED = 3000

# Safety margin: Klipper may reject moves at exact 0.0 due to
# homing position overshoot (e.g. -0.006 after G28).
# Add a small epsilon to keep coordinates safely within bounds.
_COORD_EPSILON = 0.1  # mm


def _validate_coord(x: float, y: float, z: float | None = None):
    if not (X_MIN <= x <= X_MAX):
        raise ValueError(f"X={x} out of range [{X_MIN}, {X_MAX}]")
    if not (Y_MIN <= y <= Y_MAX):
        raise ValueError(f"Y={y} out of range [{Y_MIN}, {Y_MAX}]")
    if z is not None and not (Z_MIN <= z <= Z_MAX):
        raise ValueError(f"Z={z} out of range [{Z_MIN}, {Z_MAX}]")


def _clamp_feed(feed: int, max_feed: int) -> int:
    return min(feed, max_feed)


class MotionController:
    def __init__(self, client: MoonrakerClient):
        self.client = client

    async def _safe_move_xy(self, x: float, y: float, feed: int = DEFAULT_XY_FEED):
        """Safety: raise Z to safe height, then move XY.
        Klipper 启动后处于 unhomed 状态，任何绝对移动都会被拒绝。
        遇到 'out of range' / 'must home' 时先 G28 归位再重试。
        """
        # Clamp coordinates with epsilon margin to avoid Klipper
        # "Move out of range" errors from homing overshoot (e.g. -0.006)
        x = max(X_MIN + _COORD_EPSILON, min(X_MAX - _COORD_EPSILON, x))
        y = max(Y_MIN + _COORD_EPSILON, min(Y_MAX - _COORD_EPSILON, y))
        _validate_coord(x, y)
        feed = _clamp_feed(feed, XY_MAX_FEED)
        z_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        await self.client.send_gcode("G90")
        try:
            await self.client.send_gcode(f"G1 Z{Z_SAFE} F{z_feed}")
        except DeviceConnectionError as e:
            err = str(e).lower()
            if "out of range" in err or "home" in err:
                logger.warning("[%s] Move rejected (unhomed?), auto-homing: %s", self.client.ip, e)
                await self.client.send_gcode("G28")
                # After homing, the position may slightly overshoot past 0
                # (e.g. -0.006). Move to a safe positive position first.
                try:
                    await self.client.send_gcode(
                        f"G1 X{_COORD_EPSILON:.1f} Y{_COORD_EPSILON:.1f} Z{Z_SAFE} F{z_feed}"
                    )
                except DeviceConnectionError:
                    # If even this fails, the position_min in Klipper config
                    # may allow negative values; just proceed.
                    pass
            else:
                raise
        await self.client.send_gcode(f"G1 X{x:.2f} Y{y:.2f} F{feed}")

    async def move_to(self, x: float, y: float, feed: int = DEFAULT_XY_FEED):
        await self._safe_move_xy(x, y, feed)
        logger.info("[%s] Moved to X%.2f Y%.2f", self.client.ip, x, y)

    async def tap(self, x: float, y: float, z: float = TAP_Z):
        _validate_coord(x, y, z)
        await self._safe_move_xy(x, y)
        z_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        # Lower to touch (clamp Z with epsilon to avoid out-of-range)
        z = max(Z_MIN + _COORD_EPSILON, min(Z_MAX - _COORD_EPSILON, z))
        await self.client.send_gcode(f"G1 Z{z:.2f} F{z_feed}")
        # Raise back
        await self.client.send_gcode(f"G1 Z{Z_SAFE} F{z_feed}")
        logger.info("[%s] Tap at X%.2f Y%.2f Z%.2f", self.client.ip, x, y, z)

    async def long_press(self, x: float, y: float, seconds: float, z: float = TAP_Z):
        _validate_coord(x, y, z)
        await self._safe_move_xy(x, y)
        z_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        z = max(Z_MIN + _COORD_EPSILON, min(Z_MAX - _COORD_EPSILON, z))
        await self.client.send_gcode(f"G1 Z{z:.2f} F{z_feed}")
        await self.client.send_gcode(f"G4 P{int(seconds * 1000)}")
        await self.client.send_gcode(f"G1 Z{Z_SAFE} F{z_feed}")
        logger.info("[%s] Long press %.1fs at X%.2f Y%.2f", self.client.ip, seconds, x, y)

    async def swipe(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
        duration_ms: int = 500,
        z: float = TAP_Z,
    ):
        _validate_coord(x1, y1, z)
        _validate_coord(x2, y2, z)
        await self._safe_move_xy(x1, y1)
        z_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        # Lower
        await self.client.send_gcode(f"G1 Z{z:.2f} F{z_feed}")
        # Calculate feed rate for swipe duration
        import math
        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if dist > 0 and duration_ms > 0:
            speed_mm_s = dist / (duration_ms / 1000)
            feed = _clamp_feed(int(speed_mm_s * 60), XY_MAX_FEED)
        else:
            feed = DEFAULT_XY_FEED
        await self.client.send_gcode(f"G1 X{x2:.2f} Y{y2:.2f} F{feed}")
        # Raise
        await self.client.send_gcode(f"G1 Z{Z_SAFE} F{z_feed}")
        logger.info(
            "[%s] Swipe (%.1f,%.1f)->(%.1f,%.1f) %dms",
            self.client.ip, x1, y1, x2, y2, duration_ms,
        )

    async def home(self):
        await self.client.home()
        logger.info("[%s] Homed", self.client.ip)
