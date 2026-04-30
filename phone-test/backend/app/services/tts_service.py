"""Multi-engine TTS service — Edge TTS (free, default), Tencent Cloud, Aliyun, Microsoft, custom HTTP."""
from __future__ import annotations

import asyncio
import logging
import struct
import hashlib
import hmac
import base64
import time
import json
from pathlib import Path
from abc import ABC, abstractmethod
from io import BytesIO

import aiohttp

from app.config import get_settings
from app.services.moonraker_client import _get_shared_session

logger = logging.getLogger(__name__)

WAV_DIR = Path("static/tts")


class TTSResult:
    def __init__(self, audio_data: bytes, sample_rate: int = 24000, text: str = "", is_mp3: bool = False):
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.text = text
        self.is_mp3 = is_mp3

    def save_wav(self) -> tuple[str, int]:
        WAV_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        if self.is_mp3:
            mp3_path = WAV_DIR / f"tts_{ts}.mp3"
            mp3_path.write_bytes(self.audio_data)
            duration_ms = self._estimate_duration()
            return str(mp3_path.name), duration_ms
        wav_path = WAV_DIR / f"tts_{ts}.wav"
        num_channels = 1
        sample_width = 2
        num_frames = len(self.audio_data) // (num_channels * sample_width)
        data_size = len(self.audio_data)
        with open(wav_path, "wb") as f:
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_size))
            f.write(b"WAVE")
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))
            f.write(struct.pack("<H", 1))
            f.write(struct.pack("<H", num_channels))
            f.write(struct.pack("<I", self.sample_rate))
            f.write(struct.pack("<I", self.sample_rate * num_channels * sample_width))
            f.write(struct.pack("<H", num_channels * sample_width))
            f.write(struct.pack("<H", sample_width * 8))
            f.write(b"data")
            f.write(struct.pack("<I", data_size))
            f.write(self.audio_data)
        duration_ms = int(num_frames / self.sample_rate * 1000) if self.sample_rate > 0 else 0
        return str(wav_path.name), duration_ms

    def _estimate_duration(self) -> int:
        if len(self.audio_data) < 100:
            return 0
        return int(len(self.audio_data) / 16)


class TTSEngine(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice_type: int) -> TTSResult:
        ...


# ─── Edge TTS (Free, No API Key) ──────────────────────────────────────

EDGE_VOICE_MAP = {
    1001: "zh-CN-XiaoxiaoNeural",
    1002: "zh-CN-YunxiNeural",
    1003: "zh-CN-YunyangNeural",
    1004: "zh-CN-XiaoyiNeural",
    1005: "zh-CN-XiaohanNeural",
    1006: "zh-CN-YunjianNeural",
}


class EdgeTTSEngine(TTSEngine):
    def __init__(self):
        pass

    async def synthesize(self, text: str, voice_type: int) -> TTSResult:
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts 未安装，请运行: pip install edge-tts")

        voice = EDGE_VOICE_MAP.get(voice_type, "zh-CN-XiaoxiaoNeural")
        communicate = edge_tts.Communicate(text, voice)
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        if not audio_chunks:
            raise RuntimeError("Edge TTS returned empty audio")
        mp3_data = b"".join(audio_chunks)
        return TTSResult(mp3_data, 24000, text, is_mp3=True)


# ─── Tencent Cloud TTS ────────────────────────────────────────────────

class TencentTTSEngine(TTSEngine):
    HOST = "tts.tencentcloudapi.com"
    ENDPOINT = "https://tts.tencentcloudapi.com"

    def __init__(self, secret_id: str, secret_key: str):
        self.secret_id = secret_id
        self.secret_key = secret_key

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    async def synthesize(self, text: str, voice_type: int) -> TTSResult:
        sid, skey = self.secret_id, self.secret_key
        if not sid or not skey:
            raise ValueError("腾讯云 TTS 未配置 SecretId/SecretKey")

        service = "tts"
        action = "TextToVoice"
        version = "2019-08-23"
        algorithm = "TC3-HMAC-SHA256"
        timestamp = int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))

        payload = json.dumps({
            "Text": text,
            "SessionId": f"pt-{timestamp}",
            "VoiceType": voice_type,
            "Codec": "pcm",
            "SampleRate": 16000,
        })
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{self.HOST}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"

        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical}"

        secret_date = self._sign(f"TC3{skey}".encode("utf-8"), date)
        secret_service = self._sign(secret_date, service)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = f"{algorithm} Credential={sid}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        headers = {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": self.HOST,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
            "X-TC-Region": "ap-guangzhou",
        }

        session = await _get_shared_session()
        async with session.post(self.ENDPOINT, headers=headers, data=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Tencent TTS returned {resp.status}: {await resp.text()}")
            result = await resp.json()

        resp_data = result.get("Response", {})
        error = resp_data.get("Error")
        if error:
            raise RuntimeError(f"Tencent TTS error: {error.get('Code')} - {error.get('Message')}")

        audio_base64 = resp_data.get("Audio", "")
        if not audio_base64:
            raise RuntimeError("Tencent TTS returned empty audio")
        return TTSResult(base64.b64decode(audio_base64), 16000, text)


# ─── Aliyun TTS ───────────────────────────────────────────────────────

class AliyunTTSEngine(TTSEngine):
    ENDPOINT = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"

    def __init__(self, access_key_id: str, access_key_secret: str):
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret

    async def synthesize(self, text: str, voice_type: int) -> TTSResult:
        if not self.access_key_id or not self.access_key_secret:
            raise ValueError("阿里云 TTS 未配置 AccessKeyId/AccessKeySecret")

        voice_map = {1001: "zhiyan_emo", 1002: "zhimiao_emo", 1003: "zhiyan", 1004: "xiaoyun"}
        voice_name = voice_map.get(voice_type, "zhiyan_emo")

        params = {
            "appkey": self.access_key_id,
            "text": text,
            "format": "pcm",
            "sample_rate": 16000,
            "voice": voice_name,
            "volume": 50,
            "speech_rate": 0,
            "pitch_rate": 0,
        }

        session = await _get_shared_session()
        async with session.get(
            self.ENDPOINT, params=params,
            headers={"Authorization": f"Bearer {self.access_key_secret}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Aliyun TTS returned {resp.status}: {await resp.text()}")
            pcm_data = await resp.read()

        if len(pcm_data) < 100:
            raise RuntimeError("Aliyun TTS returned empty audio")
        return TTSResult(pcm_data, 16000, text)


# ─── Microsoft Azure TTS ─────────────────────────────────────────────

class MicrosoftTTSEngine(TTSEngine):
    ENDPOINT_TEMPLATE = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def __init__(self, api_key: str, region: str = "eastasia"):
        self.api_key = api_key
        self.region = region

    async def synthesize(self, text: str, voice_type: int) -> TTSResult:
        if not self.api_key:
            raise ValueError("微软 TTS 未配置 API Key")

        voice_map = {1001: "zh-CN-XiaoxiaoNeural", 1002: "zh-CN-YunxiNeural", 1003: "zh-CN-YunyangNeural", 1004: "zh-CN-XiaoyiNeural"}
        voice_name = voice_map.get(voice_type, "zh-CN-XiaoxiaoNeural")

        ssml = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN"><voice name="{voice_name}">{text}</voice></speak>'
        endpoint = self.ENDPOINT_TEMPLATE.format(region=self.region)

        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "raw-16khz-16bit-mono-pcm",
        }

        session = await _get_shared_session()
        async with session.post(endpoint, headers=headers, data=ssml.encode("utf-8"), timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Microsoft TTS returned {resp.status}: {await resp.text()}")
            pcm_data = await resp.read()

        if len(pcm_data) < 100:
            raise RuntimeError("Microsoft TTS returned empty audio")
        return TTSResult(pcm_data, 16000, text)


# ─── Custom HTTP TTS Server ──────────────────────────────────────────

class CustomTTSEngine(TTSEngine):
    def __init__(self, url: str, auth_key: str = ""):
        self.url = url.rstrip("/")
        self.auth_key = auth_key

    async def synthesize(self, text: str, voice_type: int) -> TTSResult:
        if not self.url:
            raise ValueError("自定义 TTS 未配置服务器 URL")

        headers = {"Content-Type": "application/json"}
        if self.auth_key:
            headers["Authorization"] = f"Bearer {self.auth_key}"

        payload = json.dumps({"text": text, "voice_type": voice_type})
        session = await _get_shared_session()
        async with session.post(f"{self.url}/synthesize", headers=headers, data=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Custom TTS returned {resp.status}: {await resp.text()}")
            ct = resp.headers.get("Content-Type", "")
            if "audio" in ct or "octet-stream" in ct:
                audio_data = await resp.read()
                return TTSResult(audio_data, 16000, text)
            result = await resp.json()
            audio_b64 = result.get("audio") or result.get("data", "")
            if audio_b64:
                return TTSResult(base64.b64decode(audio_b64), result.get("sample_rate", 16000), text)
            url = result.get("audio_url") or result.get("url", "")
            if url:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as ar:
                    audio_data = await ar.read()
                    return TTSResult(audio_data, 16000, text)
            raise RuntimeError("Custom TTS: unsupported response format")


# ─── Engine Factory ───────────────────────────────────────────────────

ENGINE_MAP = {
    "edge": EdgeTTSEngine,
    "tencent": TencentTTSEngine,
    "aliyun": AliyunTTSEngine,
    "microsoft": MicrosoftTTSEngine,
    "custom": CustomTTSEngine,
}


def create_engine() -> TTSEngine:
    s = get_settings()
    engine_name = s.tts_engine.lower()
    cls = ENGINE_MAP.get(engine_name)
    if not cls:
        raise ValueError(f"Unknown TTS engine: {engine_name}. Supported: {list(ENGINE_MAP.keys())}")

    if engine_name == "edge":
        return cls()
    elif engine_name == "tencent":
        return cls(s.tts_secret_id, s.tts_secret_key)
    elif engine_name == "aliyun":
        return cls(s.tts_secret_id, s.tts_secret_key)
    elif engine_name == "microsoft":
        return cls(s.tts_secret_id, s.tts_secret_key)
    elif engine_name == "custom":
        return cls(s.tts_custom_url, s.tts_custom_key)
    return cls()


async def synthesize_and_play(text: str, voice_type: int = 0) -> dict:
    engine = create_engine()
    settings = get_settings()
    vt = voice_type if voice_type > 0 else settings.tts_voice_type
    result = await engine.synthesize(text, vt)
    filename, duration_ms = result.save_wav()
    logger.info("TTS [%s]: '%s' -> %s (%dms)", settings.tts_engine, text[:30], filename, duration_ms)
    return {"text": text, "audio_url": f"/static/tts/{filename}", "duration_ms": duration_ms, "engine": settings.tts_engine}
