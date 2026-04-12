from app.vision.adapter import VisionAdapter, TextResult, MatchResult

# Lazy imports to avoid crashing if cv2/paddleocr not installed
def _get_template_match_adapter():
    from app.vision.template_match_adapter import TemplateMatchAdapter
    return TemplateMatchAdapter

def _get_vision_manager():
    from app.vision.manager import vision_manager
    return vision_manager

__all__ = [
    "VisionAdapter", "TextResult", "MatchResult",
    "_get_template_match_adapter",
    "_get_vision_manager",
]
