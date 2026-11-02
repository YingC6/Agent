"""确定性校验规则。

不导入任何模型模块,仅按属性读取,避免与 models.schemas 形成循环导入。
"""

from __future__ import annotations

from typing import Any


def plan_contract_errors(plan: Any) -> list[str]:
    """校验行程自身的结构性约束,返回按优先级排列的错误信息。"""
    errors: list[str] = []

    if plan.start_date > plan.end_date:
        errors.append("开始日期不能晚于结束日期")
    if not plan.days:
        errors.append("行程至少包含一天")

    expected_dates = [day.date for day in plan.days]
    if len(set(expected_dates)) != len(expected_dates):
        errors.append("每日行程日期不能重复")
    if [day.day_index for day in plan.days] != list(range(len(plan.days))):
        errors.append("每日行程索引必须从0连续递增")
    if any(not 1 <= len(day.attractions) <= 3 for day in plan.days):
        errors.append("每天必须安排1至3个景点")
    if any(len({attraction.name for attraction in day.attractions}) != len(day.attractions) for day in plan.days):
        errors.append("同一天不能安排重复景点")
    if plan.budget and plan.budget.total != (
        plan.budget.total_attractions + plan.budget.total_hotels + plan.budget.total_meals + plan.budget.total_transportation
    ):
        errors.append("预算总额必须等于各项费用之和")

    return errors
