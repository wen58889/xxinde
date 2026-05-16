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

    # Vision / LLM
    vllm_base_url: str = "http://192.168.5.8:8000"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    modelscope_token: str = ""
    custom_api_base_url: str = ""
    custom_api_key: str = ""
    custom_api_model: str = ""

    # TTS
    tts_engine: str = "edge"      # edge / tencent / aliyun / microsoft / custom
    tts_secret_id: str = ""       # 腾讯云 SecretId / 阿里 AccessKeyId / 微软 API Key
    tts_secret_key: str = ""      # 腾讯云 SecretKey / 阿里 AccessKeySecret / 微软 API Region
    tts_voice_type: int = 1001    # 音色编号（各平台含义不同）
    tts_custom_url: str = ""      # 自定义TTS服务器URL（局域网自建）
    tts_custom_key: str = ""      # 自定义TTS服务器认证Key

    # N1 SSH (for TTS audio playback on device)
    n1_ssh_user: str = "root"
    n1_ssh_password: str = "1234"
    n1_audio_player: str = "ffplay"

    # Connection pool
    connection_pool_limit: int = 50
    connection_pool_limit_per_host: int = 4
    connection_pool_ttl_dns_cache: int = 300
    connection_pool_keepalive: int = 30

    # Heartbeat
    heartbeat_interval: float = 5.0
    heartbeat_max_concurrent: int = 20
    heartbeat_timeout: float = 2.0
    heartbeat_offline_skip_rounds: int = 4

    # SSH remote tool
    ssh_connect_timeout: float = 5.0
    ssh_command_timeout: float = 10.0
    ssh_max_retries: int = 2

    # Recovery strategy
    recovery_max_wait: float = 30.0
    recovery_startup_wait: float = 10.0
    recovery_window: float = 300.0
    recovery_max_attempts: int = 3
    recovery_firmware_timeout: float = 5.0
    recovery_server_restart_timeout: float = 10.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
