from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "mysql+aiomysql://root:phonetest@localhost:3306/phonetest"

    # JWT
    jwt_secret_key: str = "change-this-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Vision — OpenCV Template Matching
    template_match_threshold: float = 0.85
    template_icons_dir: str = "templates/icons"

    # Vision — PaddleOCR
    ocr_lang: str = "ch"

    # Device network
    device_ip_start: str = "192.168.5.100"
    device_ip_end: str = "192.168.5.200"
    device_moonraker_port: int = 7125
    device_camera_port: int = 1984   # go2rtc 快照端口（GET /api/streams/camera0.jpg）

    # Phone screen crop region in the camera image (after 90° rotation to 720×1280).
    # Format: "x1,y1,x2,y2" — top-left and bottom-right pixel coords.
    # Set to the rectangle that contains ONLY the phone screen (no fixture/background).
    # Leave empty to use full image (disables cropping).
    screen_crop: str = ""  # e.g. "175,50,575,900"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8080

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
