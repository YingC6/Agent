"""联网搜索触发策略:三态开关 off / auto / on。"""

from __future__ import annotations

from ..models.schemas import TripRequest

TIMELINESS_KEYWORDS = (
    "最近", "最新", "现在", "今年", "本月", "本周",
    "开放时间", "门票", "是否还", "演出", "活动", "临时", "限时", "2026",
)


def should_search_web(request: TripRequest) -> bool:
    """auto 模式只在识别到时效性需求时联网,避免无谓调用。"""
    mode = (request.search_mode or "auto").lower()
    if mode == "off":
        return False
    if mode == "on":
        return True

    text = " ".join([*(request.preferences or []), request.free_text_input or ""])
    return any(keyword in text for keyword in TIMELINESS_KEYWORDS)
