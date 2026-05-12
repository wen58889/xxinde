from __future__ import annotations

import logging
from app.services.moonraker_client import MoonrakerClient, DeviceConnectionError

logger = logging.getLogger(__name__)

X_MIN, X_MAX = 0.0, 150.0
Y_MIN, Y_MAX = 0.0, 150.0
Z_MIN, Z_MAX = -1.0, 10.0
Z_SAFE = 3.0
XY_MAX_FEED = 9000
Z_MAX_FEED = 9000
TAP_Z = -1.0
TAP_Z_FALLBACK = 0.05
TAP_Z_FEED = 6000
DEFAULT_XY_FEED = 6000
DEFAULT_Z_FEED = 6000

_COORD_EPSILON = 0.1


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
                try:
                    await self.client.send_gcode(
                        f"G1 X{_COORD_EPSILON:.1f} Y{_COORD_EPSILON:.1f} Z{Z_SAFE} F{z_feed}"
                    )
                except DeviceConnectionError:
                    pass
            else:
                raise
        await self.client.send_gcode(f"G1 X{x:.2f} Y{y:.2f} F{feed}")

    async def _tap_z(self, z: float):
        """Lower Z to tap height with fallback: if Z<0 is rejected by Klipper
        (position_min=0 in printer.cfg), retry with a safe positive Z."""
        z_feed = _clamp_feed(TAP_Z_FEED, Z_MAX_FEED)
        z_clamped = max(Z_MIN + _COORD_EPSILON, min(Z_MAX - _COORD_EPSILON, z))
        raise_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        try:
            await self.client.send_gcode(f"G1 Z{z_clamped:.2f} F{z_feed}")
            await self.client.send_gcode(f"G1 Z{Z_SAFE} F{raise_feed}")
            logger.info("[%s] Tap Z=%.2f (success)", self.client.ip, z_clamped)
        except DeviceConnectionError as e:
            err = str(e).lower()
            if "out of range" in err and z_clamped < 0:
                logger.warning(
                    "[%s] Z=%.2f rejected (Klipper position_min>=0), "
                    "falling back to Z=%.2f. "
                    "TIP: Set [stepper_z] position_min: -1 in printer.cfg for better tap force.",
                    self.client.ip, z_clamped, TAP_Z_FALLBACK,
                )
                await self.client.send_gcode(f"G1 Z{TAP_Z_FALLBACK:.2f} F{z_feed}")
                await self.client.send_gcode(f"G1 Z{Z_SAFE} F{raise_feed}")
                logger.info("[%s] Tap Z=%.2f (fallback from %.2f)", self.client.ip, TAP_Z_FALLBACK, z_clamped)
            else:
                raise

    async def move_to(self, x: float, y: float, feed: int = DEFAULT_XY_FEED):
        await self._safe_move_xy(x, y, feed)
        logger.info("[%s] Moved to X%.2f Y%.2f", self.client.ip, x, y)

    async def tap(self, x: float, y: float, z: float = TAP_Z):
        _validate_coord(x, y, z)
        await self._safe_move_xy(x, y)
        await self._tap_z(z)
        logger.info("[%s] Tap at X%.2f Y%.2f Z%.2f", self.client.ip, x, y, z)

    async def long_press(self, x: float, y: float, seconds: float, z: float = TAP_Z):
        _validate_coord(x, y, z)
        await self._safe_move_xy(x, y)
        z_feed = _clamp_feed(TAP_Z_FEED, Z_MAX_FEED)
        z_clamped = max(Z_MIN + _COORD_EPSILON, min(Z_MAX - _COORD_EPSILON, z))
        raise_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        try:
            await self.client.send_gcode(f"G1 Z{z_clamped:.2f} F{z_feed}")
        except DeviceConnectionError as e:
            err = str(e).lower()
            if "out of range" in err and z_clamped < 0:
                logger.warning("[%s] Z=%.2f rejected, fallback to Z=%.2f", self.client.ip, z_clamped, TAP_Z_FALLBACK)
                await self.client.send_gcode(f"G1 Z{TAP_Z_FALLBACK:.2f} F{z_feed}")
            else:
                raise
        await self.client.send_gcode(f"G4 P{int(seconds * 1000)}")
        await self.client.send_gcode(f"G1 Z{Z_SAFE} F{raise_feed}")
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
        z_feed = _clamp_feed(TAP_Z_FEED, Z_MAX_FEED)
        z_clamped = max(Z_MIN + _COORD_EPSILON, min(Z_MAX - _COORD_EPSILON, z))
        raise_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        try:
            await self.client.send_gcode(f"G1 Z{z_clamped:.2f} F{z_feed}")
        except DeviceConnectionError as e:
            err = str(e).lower()
            if "out of range" in err and z_clamped < 0:
                logger.warning("[%s] Z=%.2f rejected, fallback to Z=%.2f", self.client.ip, z_clamped, TAP_Z_FALLBACK)
                await self.client.send_gcode(f"G1 Z{TAP_Z_FALLBACK:.2f} F{z_feed}")
            else:
                raise
        import math
        dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if dist > 0 and duration_ms > 0:
            speed_mm_s = dist / (duration_ms / 1000)
            feed = _clamp_feed(int(speed_mm_s * 60), XY_MAX_FEED)
        else:
            feed = DEFAULT_XY_FEED
        await self.client.send_gcode(f"G1 X{x2:.2f} Y{y2:.2f} F{feed}")
        await self.client.send_gcode(f"G1 Z{Z_SAFE} F{raise_feed}")
        logger.info(
            "[%s] Swipe (%.1f,%.1f)->(%.1f,%.1f) %dms",
            self.client.ip, x1, y1, x2, y2, duration_ms,
        )

    async def home(self):
        await self.client.home()
        logger.info("[%s] Homed", self.client.ip)

    async def park_y(self):
        y_park = Y_MIN + _COORD_EPSILON
        feed = _clamp_feed(DEFAULT_XY_FEED, XY_MAX_FEED)
        z_feed = _clamp_feed(DEFAULT_Z_FEED, Z_MAX_FEED)
        await self.client.send_gcode("G90")
        await self.client.send_gcode(f"G1 Z{Z_SAFE} F{z_feed}")
        await self.client.send_gcode(f"G1 Y{y_park:.2f} F{feed}")
        logger.info("[%s] Y parked at %.2f (camera clear of screen)", self.client.ip, y_park)
