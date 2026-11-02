"""主动澄清:当需求信息不足时,先给出少量确认问题,而不是直接猜。"""

from __future__ import annotations

from ..models.schemas import TripRequest

PLAY_STYLE_QUESTION = "你更喜欢哪种玩法：自然风光、历史文化，还是美食购物？"
LONG_TRIP_QUESTION = "行程超过10天，是否需要按城市或区域分段精简？"
LONG_TRIP_DAYS = 10


def detect_clarification(request: TripRequest) -> list[str]:
    """返回需要用户补充确认的问题,空列表表示信息足够。"""
    questions: list[str] = []
    if not request.preferences and not (request.free_text_input or "").strip():
        questions.append(PLAY_STYLE_QUESTION)
    if request.travel_days > LONG_TRIP_DAYS:
        questions.append(LONG_TRIP_QUESTION)
    return questions
