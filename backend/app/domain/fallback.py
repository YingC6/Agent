"""确定性兜底行程。

当 Agent 调用或解析失败时,用纯函数构造一份结构合法、明确标记为降级的行程。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models.schemas import Attraction, DayPlan, Location, Meal, TripPlan, TripRequest
from .clarification import detect_clarification
from .scheduler import build_day_timeline


def build_fallback_plan(request: TripRequest, reason: str = "") -> TripPlan:
    """创建备用计划(当Agent失败时)。"""
    start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

    days = []
    for i in range(request.travel_days):
        current_date = start_date + timedelta(days=i)

        day_plan = DayPlan(
            date=current_date.strftime("%Y-%m-%d"),
            day_index=i,
            description=f"第{i + 1}天行程",
            transportation=request.transportation,
            accommodation=request.accommodation,
            attractions=[
                Attraction(
                    name=f"{request.city}景点{j + 1}",
                    address=f"{request.city}市",
                    location=Location(longitude=116.4 + i * 0.01 + j * 0.005, latitude=39.9 + i * 0.01 + j * 0.005),
                    visit_duration=120,
                    description=f"这是{request.city}的著名景点",
                    category="景点",
                )
                for j in range(2)
            ],
            meals=[
                Meal(type="breakfast", name=f"第{i + 1}天早餐", description="当地特色早餐"),
                Meal(type="lunch", name=f"第{i + 1}天午餐", description="午餐推荐"),
                Meal(type="dinner", name=f"第{i + 1}天晚餐", description="晚餐推荐"),
            ],
        )
        # 兜底行程也用确定性排程生成时间表,保证前端展示一致
        day_plan.timeline = build_day_timeline(day_plan)
        days.append(day_plan)

    return TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=days,
        weather_info=[],
        overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。",
        source="fallback",
        is_fallback=True,
        clarification_questions=detect_clarification(request),
        warnings=[f"AI 规划未完成，当前展示的是备用行程。{reason}".strip()],
    )
