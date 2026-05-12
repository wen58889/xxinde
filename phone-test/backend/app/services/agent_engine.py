"""AI Agent Engine — ReAct (Observe→Think→Act) loop for autonomous phone control.

The agent observes the phone screen via OCR+VLM, thinks via LLM to decide the
next action, executes it via mechanical arm, then observes again until the task
is done or max steps reached.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from app.services.moonraker_client import MoonrakerClient
from app.services.motion import MotionController
from app.services.screenshot import capture_screenshot
from app.services.coordinate import CoordinateMapper
from app.services.tts_service import synthesize_and_play
from app.services.n1_player import play_on_device
from app.vision.manager import vision_manager
from app.config import get_settings
from app.ws_manager import ws_manager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个手机自动化AI助手，能看懂手机屏幕并操控机械臂执行动作。

## 可用动作（每次只执行一个）

1. **tap(x, y)** — 点击屏幕像素坐标 (x, y)。摄像头分辨率720×1280，旋转后坐标。
2. **tap_text(text)** — 点击屏幕上包含该文字的区域。
3. **swipe(direction)** — 滑动屏幕。direction: up/down/left/right
4. **type_text(text)** — 通过TTS语音说出文字（用于语音输入场景）。
5. **long_press(x, y, seconds)** — 长按指定位置。
6. **wait(seconds)** — 等待指定秒数。
7. **done(result)** — 任务完成，result为最终结果描述。
8. **fail(reason)** — 任务失败，reason为失败原因。

## 决策规则

- 仔细观察屏幕内容，理解当前页面和上下文
- 根据任务目标决定下一步操作
- 每次只输出一个动作，格式严格为JSON
- 如果看到弹窗/错误/异常，优先处理
- 如果当前页面不是预期页面，先导航回去
- 不要重复执行相同操作超过3次

## 输出格式

严格输出JSON，不要其他文字：
{"action": "tap", "x": 360, "y": 640, "reason": "点击发送按钮"}
{"action": "tap_text", "text": "发送", "reason": "点击发送按钮"}
{"action": "swipe", "direction": "up", "reason": "向上滚动查看更多消息"}
{"action": "type_text", "text": "你好，请问有什么可以帮您的？", "reason": "回复客户消息"}
{"action": "wait", "seconds": 2, "reason": "等待页面加载"}
{"action": "done", "result": "已回复所有客户消息"}
{"action": "fail", "reason": "无法找到聊天输入框"}
"""


@dataclass
class AgentStep:
    step: int
    observation: str
    thought: str
    action: str
    action_detail: dict = field(default_factory=dict)
    result: str = ""
    timestamp: float = 0.0


class AgentEngine:
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
        self._history: list[AgentStep] = []
        self._action_counts: dict[str, int] = {}
        self._last_ocr_texts: list[str] = []
        self._last_ocr_coords: list[tuple[str, float, float]] = []
        self._task_text: str = ""

    def stop(self):
        self._stopped = True

    async def run(self, task: str, max_steps: int = 30) -> dict:
        self._stopped = False
        self._history = []
        self._action_counts = {}
        self._last_ocr_texts = []
        self._last_ocr_coords = []
        self._task_text = task
        results = {"task": task, "steps": [], "completed": False, "error": None}

        await ws_manager.broadcast("agent_status", {
            "device_id": self.device_id, "status": "running", "task": task,
        })

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"任务：{task}\n\n请开始执行。"},
        ]

        for i in range(max_steps):
            if self._stopped:
                results["error"] = "Agent stopped by user"
                break

            try:
                observation = await self._observe()

                await ws_manager.broadcast("agent_observe", {
                    "device_id": self.device_id,
                    "step": i + 1,
                    "observation": observation[:300],
                })

                step = AgentStep(
                    step=i + 1,
                    observation=observation,
                    thought="",
                    action="",
                    timestamp=time.time(),
                )

                messages.append({"role": "assistant", "content": f"[观察] {observation}"})

                thought, action_dict = await self._think(messages, observation)

                await ws_manager.broadcast("agent_think", {
                    "device_id": self.device_id,
                    "step": i + 1,
                    "thought": thought[:300],
                    "action": action_dict.get("action", ""),
                })

                step.thought = thought
                step.action = action_dict.get("action", "")
                step.action_detail = action_dict

                action_result = await self._act(action_dict)
                step.result = action_result

                messages.append({"role": "user", "content": f"[动作结果] {action_result}"})

                self._history.append(step)
                results["steps"].append({
                    "step": step.step,
                    "observation": step.observation[:200],
                    "thought": step.thought[:200],
                    "action": step.action,
                    "result": step.result[:200],
                })

                await ws_manager.broadcast("agent_step", {
                    "device_id": self.device_id,
                    "step": i + 1,
                    "observation": step.observation[:300],
                    "thought": step.thought[:300],
                    "action": step.action,
                    "action_detail": step.action_detail,
                    "result": step.result[:200],
                    "timestamp": step.timestamp,
                })

                if step.action in ("done", "fail"):
                    results["completed"] = step.action == "done"
                    if step.action == "fail":
                        results["error"] = action_dict.get("reason", "Agent reported failure")
                    break

                repeat_key = f"{step.action}_{json.dumps({k:v for k,v in action_dict.items() if k != 'reason'}, sort_keys=True, default=str)}"
                self._action_counts[repeat_key] = self._action_counts.get(repeat_key, 0) + 1
                if self._action_counts[repeat_key] >= 3:
                    results["error"] = f"Repeated action too many times: {step.action}"
                    break

            except Exception as e:
                logger.error("[%d] Agent step %d error: %s", self.device_id, i + 1, e)
                results["error"] = str(e)
                try:
                    await self.motion.client.send_gcode("G1 Z3 F3000")
                except Exception:
                    pass
                break

        try:
            await self.motion.park_y()
        except Exception:
            pass

        await ws_manager.broadcast("agent_status", {
            "device_id": self.device_id,
            "status": "done" if results["completed"] else "error",
            "steps": len(results["steps"]),
        })

        return results

    async def _observe(self) -> str:
        await self.motion.park_y()
        screenshot = await capture_screenshot(self.device_ip)

        parts = []

        try:
            texts = await vision_manager.read_text(screenshot)
            if texts:
                self._last_ocr_texts = [t.text for t in texts]
                self._last_ocr_coords = [(t.text, t.x, t.y) for t in texts]
                lines = [f"  ({int(t.x)},{int(t.y)}) {t.text}" for t in texts[:30]]
                parts.append("屏幕文字(OCR):\n" + "\n".join(lines))
                if len(texts) > 30:
                    parts.append(f"  ...共{len(texts)}处文字")
        except Exception as e:
            parts.append(f"OCR失败: {e}")

        simple_task = any(k in self._task_text for k in ['点击', '打开', '进入', '找到', '点', '按'])
        if not simple_task:
            try:
                targets = await vision_manager.detect_targets(screenshot, app_name="", threshold=0.7)
                if targets:
                    tgt_lines = [f"  {t.label} ({int(t.x)},{int(t.y)}) conf={t.confidence:.2f}" for t in targets[:15]]
                    parts.append("识别到的UI元素:\n" + "\n".join(tgt_lines))
            except Exception:
                pass

            try:
                anomaly = await vision_manager.detect_anomaly(screenshot)
                if anomaly:
                    parts.append(f"⚠️ 异常检测: {anomaly}")
            except Exception:
                pass

        return "\n\n".join(parts) if parts else "屏幕内容无法识别"

    async def _think(self, messages: list, observation: str) -> tuple[str, dict]:
        import re

        simple_patterns = r'(点击|打开|进入|找到|搜索|点|按|tap|open|click|find)'
        if re.search(simple_patterns, self._task_text):
            fallback = self._ocr_fallback(messages, observation)
            if fallback:
                logger.info("Simple task + OCR match, skipping LLM: %s", fallback)
                raw = json.dumps(fallback, ensure_ascii=False)
                action_dict = self._parse_action(raw)
                return raw[:300], action_dict

        raw = ""

        try:
            from app.vision.api_vision import APIVisionAdapter
            adapter = APIVisionAdapter()
            screenshot = await capture_screenshot(self.device_ip)
            raw = await asyncio.wait_for(
                adapter._chat(
                    prompt=f"当前任务上下文：\n{messages[-3:] if len(messages) > 3 else messages}\n\n当前屏幕观察：{observation}\n\n请决定下一步动作，严格输出JSON格式的action。",
                    images=[screenshot],
                    max_tokens=256,
                ),
                timeout=5.0,
            )
        except Exception as e:
            logger.warning("VLM think failed (%s), trying text LLM...", type(e).__name__)
            raw = ""

        if not raw:
            try:
                raw = await asyncio.wait_for(
                    self._call_text_llm(messages, observation),
                    timeout=5.0,
                )
            except Exception as e:
                logger.warning("Text LLM failed (%s), using OCR fallback", type(e).__name__)
                raw = ""

        if not raw:
            fallback = self._ocr_fallback(messages, observation)
            if fallback:
                raw = json.dumps(fallback, ensure_ascii=False)
                logger.info("LLM unavailable, using OCR fallback: %s", fallback)
            else:
                raw = '{"action": "fail", "reason": "LLM不可用且OCR未匹配到任务关键词"}'

        action_dict = self._parse_action(raw)
        thought = raw[:300]
        return thought, action_dict

    def _ocr_fallback(self, messages: list, observation: str) -> dict | None:
        import re
        task = self._task_text
        ocr_texts = self._last_ocr_texts
        if not task or not ocr_texts:
            return None

        task_clean = re.sub(r'[帮我点击打开进入找到搜索]', '', task).strip()
        if not task_clean:
            task_clean = task

        for ocr_text in ocr_texts:
            if task_clean in ocr_text or ocr_text in task_clean:
                return {"action": "tap_text", "text": ocr_text, "reason": f"OCR匹配: 任务含'{task_clean}'→屏幕文字'{ocr_text}'"}

        task_chars = set(task_clean)
        for ocr_text in ocr_texts:
            ocr_chars = set(ocr_text)
            overlap = len(task_chars & ocr_chars)
            if overlap >= max(len(task_chars) * 0.6, 2):
                return {"action": "tap_text", "text": ocr_text, "reason": f"OCR模糊匹配(overlap={overlap}): '{ocr_text}'"}

        return None

    async def _call_text_llm(self, messages: list, observation: str) -> str:
        import aiohttp
        settings = get_settings()

        base_url = settings.custom_api_base_url or settings.vllm_base_url
        if not base_url:
            raise ValueError("No LLM endpoint configured")

        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        api_key = settings.custom_api_key or settings.openai_api_key or ""
        model = settings.custom_api_model or "default"

        llm_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        for m in messages[-8:]:
            llm_messages.append({"role": m["role"], "content": m["content"][:500]})

        payload = {
            "model": model,
            "messages": llm_messages,
            "max_tokens": 256,
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        from app.services.moonraker_client import _get_shared_session
        session = await _get_shared_session()
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"LLM returned {resp.status}")
            data = await resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _parse_action(self, raw: str) -> dict:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        for prefix in ["Action:", "action:", '{"action"']:
            idx = text.find(prefix)
            if idx > 0:
                text = text[idx:]

        try:
            result = json.loads(text.strip())
            if "action" in result:
                return result
        except json.JSONDecodeError:
            pass

        import re
        m = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

        return {"action": "wait", "seconds": 1, "reason": f"Parse failed: {raw[:100]}"}

    async def _act(self, action_dict: dict) -> str:
        action = action_dict.get("action", "")
        reason = action_dict.get("reason", "")

        if action == "tap":
            x, y = action_dict.get("x", 360), action_dict.get("y", 640)
            mx, my = self.coord.pixel_to_mech(x, y)
            await self.motion.tap(mx, my)
            return f"点击 ({x},{y}) → mech({mx:.1f},{my:.1f})"

        elif action == "tap_text":
            text = action_dict.get("text", "")
            if not text:
                return "tap_text: 缺少text参数"
            matched = None
            for ocr_text, ocr_x, ocr_y in self._last_ocr_coords:
                if text in ocr_text or ocr_text in text:
                    matched = (ocr_x, ocr_y, ocr_text)
                    break
            if matched:
                mx, my = self.coord.pixel_to_mech(matched[0], matched[1])
                await self.motion.tap(mx, my)
                return f"点击文字'{matched[2]}' at ({int(matched[0])},{int(matched[1])})"
            await self.motion.park_y()
            screenshot = await capture_screenshot(self.device_ip)
            text_coords = await vision_manager.read_text(screenshot)
            for t in text_coords:
                if text in t.text:
                    mx, my = self.coord.pixel_to_mech(t.x, t.y)
                    await self.motion.tap(mx, my)
                    return f"点击文字'{t.text}' at ({int(t.x)},{int(t.y)})"
            return f"未找到文字'{text}'"

        elif action == "swipe":
            direction = action_dict.get("direction", "up")
            start_end = {
                "up": ([50, 80], [50, 20]),
                "down": ([50, 20], [50, 80]),
                "left": ([80, 50], [20, 50]),
                "right": ([20, 50], [80, 50]),
            }
            start, end = start_end.get(direction, ([50, 80], [50, 20]))
            x1, y1 = start[0] / 100 * 720, start[1] / 100 * 1280
            x2, y2 = end[0] / 100 * 720, end[1] / 100 * 1280
            mx1, my1 = self.coord.pixel_to_mech(x1, y1)
            mx2, my2 = self.coord.pixel_to_mech(x2, y2)
            await self.motion.swipe(mx1, my1, mx2, my2, 500)
            return f"滑动 {direction}"

        elif action == "type_text":
            text = action_dict.get("text", "")
            if not text:
                return "type_text: 缺少text参数"
            try:
                result = await synthesize_and_play(text, 0)
                from pathlib import Path
                local_path = str(Path("static/tts") / result["audio_url"].split("/")[-1])
                await play_on_device(self.device_ip, local_path)
                return f"TTS播放: '{text[:30]}' ({result['duration_ms']}ms)"
            except Exception as e:
                return f"TTS失败: {e}"

        elif action == "long_press":
            x, y = action_dict.get("x", 360), action_dict.get("y", 640)
            seconds = action_dict.get("seconds", 1)
            mx, my = self.coord.pixel_to_mech(x, y)
            await self.motion.long_press(mx, my, seconds)
            return f"长按 ({x},{y}) {seconds}s"

        elif action == "wait":
            seconds = action_dict.get("seconds", 1)
            await asyncio.sleep(seconds)
            return f"等待 {seconds}s"

        elif action == "done":
            return f"任务完成: {action_dict.get('result', '')}"

        elif action == "fail":
            return f"任务失败: {action_dict.get('reason', '')}"

        else:
            return f"未知动作: {action}"
