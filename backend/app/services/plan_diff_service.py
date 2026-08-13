"""行程差异对比服务

对比优化前后的 TripPlan,生成结构化的差异摘要,供前端展示变更预览。

差异类型:
- added:    新增的景点/餐饮
- removed:  删除的景点/餐饮
- modified: 变更的景点(如游览时长、门票价格变化)
- moved:    景点移动到其他日期

输出结构:
{
    "summary": "共变更5处:新增2个景点,删除1个景点,修改2处景点",
    "days": [
        {
            "day_index": 0,
            "added_attractions": ["故宫"],
            "removed_attractions": ["天坛"],
            "modified_attractions": [{"name": "颐和园", "field": "visit_duration", "old_value": 120, "new_value": 180}],
            "moved_from": [],
            "moved_to": []
        }
    ],
    "budget_change": {"old": 580, "new": 650, "delta": 70},
    "stats": {"added": 2, "removed": 1, "modified": 2, "moved": 0}
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models.schemas import TripPlan


@dataclass
class DayDiff:
    """单日行程差异。"""
    day_index: int
    added_attractions: list[str] = field(default_factory=list)
    removed_attractions: list[str] = field(default_factory=list)
    modified_attractions: list[dict[str, Any]] = field(default_factory=list)
    added_meals: list[str] = field(default_factory=list)
    removed_meals: list[str] = field(default_factory=list)
    moved_from: list[str] = field(default_factory=list)
    moved_to: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_index": self.day_index,
            "added_attractions": self.added_attractions,
            "removed_attractions": self.removed_attractions,
            "modified_attractions": self.modified_attractions,
            "added_meals": self.added_meals,
            "removed_meals": self.removed_meals,
            "moved_from": self.moved_from,
            "moved_to": self.moved_to,
        }


def _attraction_key(attraction: Any) -> str:
    """景点的唯一标识,优先用 poi_id,否则用名称。"""
    poi_id = getattr(attraction, "poi_id", None)
    if poi_id:
        return f"poi:{poi_id}"
    return f"name:{attraction.name}"


def _diff_attraction(old_attr: Any, new_attr: Any) -> list[dict[str, Any]]:
    """对比单个景点的字段变化,返回扁平的变更列表。

    每个变更条目格式: {"name": "颐和园", "field": "visit_duration", "old_value": 120, "new_value": 180}
    与前端 AttractionChange 类型定义一致。无变化返回空列表。
    """
    changes: list[dict[str, Any]] = []
    fields_to_compare = ["visit_duration", "ticket_price", "category", "description"]

    for field_name in fields_to_compare:
        old_val = getattr(old_attr, field_name, None)
        new_val = getattr(new_attr, field_name, None)
        if old_val != new_val:
            changes.append({
                "name": old_attr.name,
                "field": field_name,
                "old_value": old_val,
                "new_value": new_val,
            })

    return changes


def compute_plan_diff(old_plan: TripPlan, new_plan: TripPlan) -> dict[str, Any]:
    """对比两个 TripPlan,返回结构化差异。

    Args:
        old_plan: 优化前的行程
        new_plan: 优化后的行程

    Returns:
        包含 summary、days、budget_change、stats 的差异字典
    """
    old_days = {day.day_index: day for day in old_plan.days}
    new_days = {day.day_index: day for day in new_plan.days}

    # 收集所有景点,用于检测跨天移动
    old_attractions_by_key: dict[str, tuple[int, Any]] = {}
    for day_index, day in old_days.items():
        for attr in day.attractions:
            old_attractions_by_key[_attraction_key(attr)] = (day_index, attr)

    new_attractions_by_key: dict[str, tuple[int, Any]] = {}
    for day_index, day in new_days.items():
        for attr in day.attractions:
            new_attractions_by_key[_attraction_key(attr)] = (day_index, attr)

    day_diffs: list[DayDiff] = []
    stats = {"added": 0, "removed": 0, "modified": 0, "moved": 0}

    all_day_indices = sorted(set(old_days.keys()) | set(new_days.keys()))

    for day_index in all_day_indices:
        old_day = old_days.get(day_index)
        new_day = new_days.get(day_index)
        diff = DayDiff(day_index=day_index)

        if old_day is None and new_day is not None:
            # 新增的日期
            diff.added_attractions = [a.name for a in new_day.attractions]
            diff.added_meals = [m.name for m in new_day.meals]
            stats["added"] += len(diff.added_attractions)
        elif old_day is not None and new_day is None:
            # 删除的日期
            diff.removed_attractions = [a.name for a in old_day.attractions]
            diff.removed_meals = [m.name for m in old_day.meals]
            stats["removed"] += len(diff.removed_attractions)
        elif old_day is not None and new_day is not None:
            old_attrs_by_key = {_attraction_key(a): a for a in old_day.attractions}
            new_attrs_by_key = {_attraction_key(a): a for a in new_day.attractions}

            # 新增景点
            for key, attr in new_attrs_by_key.items():
                if key not in old_attrs_by_key:
                    # 检查是否从其他天移动过来
                    if key in old_attractions_by_key:
                        diff.moved_to.append(attr.name)
                        stats["moved"] += 1
                    else:
                        diff.added_attractions.append(attr.name)
                        stats["added"] += 1

            # 删除景点
            for key, attr in old_attrs_by_key.items():
                if key not in new_attrs_by_key:
                    # 检查是否移动到其他天
                    if key in new_attractions_by_key:
                        diff.moved_from.append(attr.name)
                    else:
                        diff.removed_attractions.append(attr.name)
                        stats["removed"] += 1

            # 修改景点:_diff_attraction 返回扁平列表,每个字段变更一个条目
            for key, old_attr in old_attrs_by_key.items():
                if key in new_attrs_by_key:
                    changes = _diff_attraction(old_attr, new_attrs_by_key[key])
                    if changes:
                        diff.modified_attractions.extend(changes)
                        stats["modified"] += len(changes)

            # 餐饮变化
            old_meal_names = {m.name for m in old_day.meals}
            new_meal_names = {m.name for m in new_day.meals}
            diff.added_meals = list(new_meal_names - old_meal_names)
            diff.removed_meals = list(old_meal_names - new_meal_names)

        if any([diff.added_attractions, diff.removed_attractions, diff.modified_attractions,
                diff.added_meals, diff.removed_meals, diff.moved_from, diff.moved_to]):
            day_diffs.append(diff)

    # 预算变化
    budget_change = None
    old_budget = old_plan.budget.total if old_plan.budget else 0
    new_budget = new_plan.budget.total if new_plan.budget else 0
    if old_budget != new_budget:
        budget_change = {
            "old": old_budget,
            "new": new_budget,
            "delta": new_budget - old_budget,
        }

    # 生成摘要文本
    parts = []
    if stats["added"]:
        parts.append(f"新增{stats['added']}个景点")
    if stats["removed"]:
        parts.append(f"删除{stats['removed']}个景点")
    if stats["modified"]:
        parts.append(f"修改{stats['modified']}处景点")
    if stats["moved"]:
        parts.append(f"移动{stats['moved']}个景点到其他日期")
    if budget_change:
        delta_text = f"预算{'增加' if budget_change['delta'] > 0 else '减少'}{abs(budget_change['delta'])}元"
        parts.append(delta_text)

    # 预算变化也计入总变更数,避免"共变更0处"与实际有变更矛盾
    total_changes = sum(stats.values()) + (1 if budget_change else 0)
    summary = f"共变更{total_changes}处:" + "、".join(parts) if parts else "无变更"

    return {
        "summary": summary,
        "days": [d.to_dict() for d in day_diffs],
        "budget_change": budget_change,
        "stats": stats,
    }
