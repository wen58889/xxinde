from __future__ import annotations

import base64
import json
import logging
import re
import aiohttp

from app.vision.adapter import VisionAdapter, TextResult, VisionTarget
from app.config import get_settings
from app.services.moonraker_client import _get_shared_session

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


def _encode_image(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


class APIVisionAdapter(VisionAdapter):
    """Fallback adapter using OpenAI, Anthropic, or any OpenAI-compatible Vision API."""

    def __init__(self, provider: str = "openai"):
        self.provider = provider
        settings = get_settings()
        if provider == "openai":
            self.api_key = settings.openai_api_key
            self.base_url = "https://api.openai.com/v1/chat/completions"
            self.model = "gpt-4o"
        elif provider == "modelscope":
            # ModelScope 免费推理 API — GUI-Owl-1.5-8B-Instruct（与本地 vLLM 同款模型）
            self.api_key = settings.modelscope_token
            self.base_url = "https://api-inference.modelscope.cn/v1/chat/completions"
            self.model = "iic/GUI-Owl-1.5-8B-Instruct"
        elif provider == "custom":
            self.api_key = settings.custom_api_key
            self.base_url = f"{settings.custom_api_base_url.rstrip('/')}/chat/completions"
            self.model = settings.custom_api_model
        else:
            self.api_key = settings.anthropic_api_key
            self.base_url = "https://api.anthropic.com/v1/messages"
            self.model = "claude-sonnet-4-20250514"

    @staticmethod
    def _strip_think(text: str) -> str:
        """Remove <think>...</think> blocks emitted by reasoning models (MiniMax, DeepSeek-R1, etc.)."""
        import re as _re
        return _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()

    async def _call_openai(self, prompt: str, images: list[bytes], max_tokens: int = 512) -> str:
        content = []
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{_encode_image(img)}"},
            })
        content.append({"type": "text", "text": prompt})

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        session = await _get_shared_session()
        async with session.post(
            self.base_url, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS),
        ) as resp:
            data = await resp.json()
            raw = data["choices"][0]["message"]["content"]
            return self._strip_think(raw)

    async def _call_anthropic(self, prompt: str, images: list[bytes], max_tokens: int = 512) -> str:
        content = []
        for img in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": _encode_image(img)},
            })
        content.append({"type": "text", "text": prompt})

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        session = await _get_shared_session()
        async with session.post(
            self.base_url, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS),
        ) as resp:
            data = await resp.json()
            return data["content"][0]["text"]

    async def _chat(self, prompt: str, images: list[bytes], max_tokens: int = 512) -> str:
        if self.provider in {"openai", "custom"}:
            return await self._call_openai(prompt, images, max_tokens)
        return await self._call_anthropic(prompt, images, max_tokens)

    def _parse_coords(self, text: str) -> tuple[float, float] | None:
        for p in [r"\((\d+\.?\d*)\s*,\s*(\d+\.?\d*)\)", r"(\d+\.?\d*)\s*,\s*(\d+\.?\d*)"]:
            match = re.search(p, text)
            if match:
                return (float(match.group(1)), float(match.group(2)))
        return None

    def _parse_bool(self, text: str) -> bool:
        t = text.lower().strip()
        return any(w in t for w in ["yes", "是", "true", "成功"])

    async def find_icon(self, screenshot: bytes, icon_name: str) -> tuple[float, float] | None:
        result = await self._chat(f"Find the center coordinates of '{icon_name}' icon. Reply: (x, y)", [screenshot])
        return self._parse_coords(result)

    async def find_element(self, screenshot: bytes, element_desc: str) -> tuple[float, float] | None:
        result = await self._chat(f"Find the center coordinates of '{element_desc}'. Reply: (x, y)", [screenshot])
        return self._parse_coords(result)

    async def detect_page_state(self, screenshot: bytes, description: str) -> bool:
        result = await self._chat(f"Does the screen match: '{description}'? Reply yes or no.", [screenshot], 64)
        return self._parse_bool(result)

    async def verify_action(self, before: bytes, after: bytes, action_desc: str) -> bool:
        result = await self._chat(
            f"Compare before/after screenshots. Action: '{action_desc}'. Did it succeed? yes/no.",
            [before, after], 64,
        )
        return self._parse_bool(result)

    async def read_text(self, screenshot: bytes, region: list[float] | None = None) -> list[TextResult]:
        result = await self._chat("OCR: list all text on screen as JSON [{\"text\":\"...\"}]", [screenshot], 1024)
        try:
            match = re.search(r"\[.*\]", result, re.DOTALL)
            if match:
                items = json.loads(match.group())
                return [TextResult(text=i["text"], x=i.get("x", 0), y=i.get("y", 0)) for i in items]
        except (json.JSONDecodeError, KeyError):
            pass
        return [TextResult(text=result.strip(), x=0, y=0)]

    async def detect_anomaly(self, screenshot: bytes) -> str | None:
        result = await self._chat("Any popups, errors or anomalies? Reply 'none' or describe.", [screenshot], 256)
        if "none" in result.lower() or "无异常" in result:
            return None
        return result.strip()

    async def detect_targets(self, screenshot: bytes) -> list[VisionTarget]:
        # Markers that indicate the model is text-only and couldn't see the image
        _VISION_FAIL_PHRASES = (
            "no image", "without seeing", "no screenshot", "cannot see",
            "can't see", "don't have access to the image", "unable to see",
            "unable to detect", "haven't been provided", "not provided",
            "没有图片", "看不到", "无法看到", "未提供图片",
        )

        result = await self._chat(
            "Detect all interactive targets in this mobile screenshot (icons, buttons, inputs, tabs, menus). "
            "Return ONLY JSON array, each item: "
            '{"label":"name","x":0,"y":0,"w":0,"h":0,"kind":"icon|button|input|tab|menu|other","confidence":0.0}. '
            "x,y are center pixel coordinates. Do NOT include any explanation.",
            [screenshot],
            1024,
        )
        # Detect text-only model (MiniMax M2.7, etc.) that can't process images
        lower = result.lower()
        if any(phrase in lower for phrase in _VISION_FAIL_PHRASES):
            raise RuntimeError(
                f"模型 '{self.model}' 是纯文本模型，不支持视觉识别。"
                "请在参数页配置支持视觉的 API（OpenAI gpt-4o / Anthropic claude-sonnet / 其他视觉模型）"
            )
        try:
            match = re.search(r"\[.*\]", result, re.DOTALL)
            if not match:
                return []
            items = json.loads(match.group())
            targets: list[VisionTarget] = []
            for i in items:
                targets.append(
                    VisionTarget(
                        label=str(i.get("label", "target")),
                        x=float(i.get("x", 0)),
                        y=float(i.get("y", 0)),
                        w=max(float(i.get("w", 0)), 16.0),
                        h=max(float(i.get("h", 0)), 16.0),
                        kind=str(i.get("kind", "other")),
                        confidence=float(i.get("confidence", 0.0)),
                    )
                )
            return targets
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return []

    async def describe(self, screenshot: bytes) -> str:
        result = await self._chat(
            "描述这张手机截图中看到的内容：当前应用、界面元素、文字、图标和整体状态。用中文回答，3-6句话。",
            [screenshot], max_tokens=512,
        )
        return result.strip()
