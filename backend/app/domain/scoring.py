"""行程质量打分:用确定性规则给行程打 0-100 分。

只有分数低于阈值时才触发备选行程生成,平时不增加任何模型调用。
"""

from __future__ import annotations

from ..models.schemas import TripPlan, TripRequest


def score_plan(plan: TripPlan, request: TripRequest) -> int:
    """规则打分,便于解释:每违例一次扣固定分,最后限制在 0-100。"""
    if plan.is_fallback:
        return 0

    score = 100
    if len(plan.days) != request.travel_days:
        score -= 20

    names = [attraction.name for day in plan.days for attraction in day.attractions]
    if len(set(names)) != len(names):
        score -= 15

    for day in plan.days:
        if len(day.attractions) < 2:
            score -= 10
        if len(day.meals) < 3:
            score -= 5
        if day.estimated_transit_minutes > 300:
            score -= 10

    if plan.budget is None or plan.budget.total <= 0:
        score -= 10

    if request.preferences and not _covers_preferences(plan, request.preferences):
        score -= 10

    return max(0, min(score, 100))


def _covers_preferences(plan: TripPlan, preferences: list[str]) -> bool:
    """景点名称/描述/类别中至少命中一个偏好关键词。"""
    text = " ".join(
        f"{attraction.name} {attraction.description} {attraction.category}"
        for day in plan.days
        for attraction in day.attractions
    )
    return any(preference in text for preference in preferences)
