import logging

logger = logging.getLogger(__name__)


async def parse_natural_instruction(instruction: str) -> str:
    """Convert natural language instruction to YAML flow template.

    Uses pattern matching for common instructions.
    Vision: OpenCV template matching + PaddleOCR (no AI inference).
    """
    instruction = instruction.strip()
    lines = ["app: custom", "steps:"]

    lower = instruction.lower()

    if "打开" in instruction and "点" in instruction:
        parts = instruction.split("打开", 1)[1]
        if "点" in parts:
            app_part, action_part = parts.split("点", 1)
            app_name = app_part.strip()
            target = action_part.replace("一下", "").replace("击", "").strip()
            lines[0] = f"app: {app_name}"
            lines.append(f"  - action: tap_icon")
            lines.append(f"    template: {app_name}")
            lines.append(f"    threshold: 0.85")
            lines.append(f"    wait: 2")
            lines.append(f"  - action: detect_state")
            lines.append(f"    ocr_keywords: [{app_name}]")
            lines.append(f"    timeout: 5")
            if target:
                lines.append(f"  - action: tap_icon")
                lines.append(f"    template: {target}")
                lines.append(f"    threshold: 0.80")
                lines.append(f"    wait: 1")
    elif "滑" in instruction:
        import re
        count = 1
        interval = 1
        match = re.search(r"(\d+)\s*次", instruction)
        if match:
            count = int(match.group(1))
        match = re.search(r"等\s*(\d+)\s*秒", instruction)
        if match:
            interval = int(match.group(1))

        direction = "up"
        if "下" in instruction:
            direction = "down"
        elif "左" in instruction:
            direction = "left"
        elif "右" in instruction:
            direction = "right"

        lines.append(f"  - action: swipe")
        lines.append(f"    direction: {direction}")
        lines.append(f"    duration: 0.5")
        lines.append(f"    repeat: {count}")
        lines.append(f"    wait: {interval}")
    elif "暂停" in lower or "停止" in lower:
        return "__EMERGENCY_STOP__"
    else:
        # Generic: try template match then OCR fallback
        lines.append(f"  - action: tap_icon")
        lines.append(f"    template: {instruction}")
        lines.append(f"    threshold: 0.80")
        lines.append(f"    wait: 1")

    return "\n".join(lines)
