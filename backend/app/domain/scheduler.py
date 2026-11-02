"""时间表排程:把一天的景点、通勤、三餐排成可读时间轴。

纯确定性逻辑,不调用模型,方便阅读与测试。
"""

from __future__ import annotations

from ..models.schemas import DayPlan, TimelineItem

BREAKFAST_TIME = "08:00"
DAY_START_MINUTES = 8 * 60 + 30
LUNCH_TIME = 12 * 60
DINNER_TIME = 18 * 60
DEFAULT_VISIT_MINUTES = 120
DEFAULT_TRANSIT_MINUTES = 20
MEAL_MINUTES = 45


def _format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _meal_item(day: DayPlan, meal_type: str, default_title: str) -> TimelineItem:
    meal = next((item for item in day.meals if item.type == meal_type), None)
    return TimelineItem(
        time="",
        title=(meal.name if meal and meal.name else default_title),
        category="meal",
        duration_minutes=MEAL_MINUTES,
        detail=(meal.description if meal else ""),
    )


def build_day_timeline(day: DayPlan) -> list[TimelineItem]:
    """按景点顺序生成时间轴:早餐 → 景点(含通勤) → 午餐 → 景点 → 晚餐。"""
    items = [_meal_item(day, "breakfast", "早餐")]
    items[0].time = BREAKFAST_TIME

    clock = DAY_START_MINUTES
    lunch_placed = False
    for index, attraction in enumerate(day.attractions):
        if index > 0:
            transit_minutes = DEFAULT_TRANSIT_MINUTES
            if index - 1 < len(day.route_segments):
                transit_minutes = day.route_segments[index - 1].duration_minutes or DEFAULT_TRANSIT_MINUTES
            items.append(TimelineItem(
                time=_format_time(clock),
                title=f"前往{attraction.name}",
                category="transit",
                duration_minutes=transit_minutes,
                detail=f"{day.transportation}出行",
            ))
            clock += transit_minutes

        if not lunch_placed and clock >= LUNCH_TIME:
            lunch = _meal_item(day, "lunch", "午餐")
            lunch.time = _format_time(clock)
            items.append(lunch)
            clock += MEAL_MINUTES
            lunch_placed = True

        visit_minutes = attraction.visit_duration or DEFAULT_VISIT_MINUTES
        items.append(TimelineItem(
            time=_format_time(clock),
            title=attraction.name,
            category="attraction",
            duration_minutes=visit_minutes,
            detail=attraction.description,
        ))
        clock += visit_minutes

    if not lunch_placed:
        lunch = _meal_item(day, "lunch", "午餐")
        lunch.time = _format_time(max(clock, LUNCH_TIME))
        items.append(lunch)
        clock = max(clock, LUNCH_TIME) + MEAL_MINUTES

    dinner = _meal_item(day, "dinner", "晚餐")
    dinner.time = _format_time(max(clock, DINNER_TIME))
    items.append(dinner)
    return items
