from __future__ import annotations

from dataclasses import dataclass

from ..models.schemas import TripPlan, TripRequest


@dataclass(frozen=True)
class PlanValidationResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


def validate_plan_execution(plan: TripPlan, request: TripRequest) -> PlanValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if plan.city != request.city:
        errors.append(f"行程城市与请求不一致：{plan.city}")
    if plan.start_date != request.start_date or plan.end_date != request.end_date:
        errors.append("行程日期范围与请求不一致")
    if len(plan.days) != request.travel_days:
        errors.append(f"行程天数不一致：期望{request.travel_days}天，实际{len(plan.days)}天")

    seen_attractions: set[str] = set()
    for day in plan.days:
        if day.transportation != request.transportation:
            warnings.append(f"第{day.day_index + 1}天交通方式与请求不一致")
        if day.estimated_transit_minutes > 300:
            warnings.append(f"第{day.day_index + 1}天通勤时间较长：{day.estimated_transit_minutes}分钟")
        if len(day.attractions) > 2 and day.estimated_transit_minutes > 180:
            warnings.append(f"第{day.day_index + 1}天景点和通勤安排可能过于紧凑")
        for attraction in day.attractions:
            normalized_name = attraction.name.strip().lower()
            if normalized_name in seen_attractions:
                errors.append(f"景点重复安排：{attraction.name}")
            seen_attractions.add(normalized_name)

    if plan.budget and plan.budget.total < 0:
        errors.append("预算总额不能为负数")

    return PlanValidationResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
    )
