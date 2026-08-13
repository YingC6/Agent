"""出行清单服务

提供清单的 CRUD 和 AI 自动生成能力。

AI 生成策略:
- 根据行程城市、天数、交通方式、季节、偏好等信息
- 调用 LLM 生成分类清单(证件/衣物/电子/药品/其他)
- 解析 JSON 后批量写入数据库
- 生成失败时回退到通用模板
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.db_models import TripChecklist, TripRecord
from ..models.schemas import TripPlan
from .llm_service import get_llm

# 清单分类常量
CATEGORIES = ["证件", "衣物", "电子", "药品", "其他"]

# 通用兜底清单(生成失败时使用)
FALLBACK_CHECKLIST = [
    ("证件", "身份证"),
    ("证件", "机票/火车票确认信息"),
    ("衣物", "换洗衣物(按天数准备)"),
    ("衣物", "舒适步行鞋"),
    ("电子", "手机充电器"),
    ("电子", "充电宝"),
    ("药品", "常用药品(感冒/肠胃/创可贴)"),
    ("其他", "雨伞"),
    ("其他", "水杯"),
]

# AI 生成清单提示词
CHECKLIST_PROMPT = """你是出行准备专家。请根据旅行信息生成出行清单,只返回JSON数组,每个元素格式:{{"category":"分类","content":"物品名"}}。
分类必须是:证件、衣物、电子、药品、其他 之一。
数量控制在 12-18 项,根据目的地和季节调整。
旅行信息:城市={city},天数={days}天,交通={transportation},住宿={accommodation},偏好={preferences},日期={start_date}至{end_date}"""


def checklist_to_dict(item: TripChecklist) -> dict[str, Any]:
    return {
        "id": item.id,
        "trip_id": item.trip_id,
        "category": item.category,
        "content": item.content,
        "is_checked": item.is_checked,
        "sort_order": item.sort_order,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def list_checklist(db: Session, trip_id: int) -> list[TripChecklist]:
    """查询指定行程的清单条目,按分类和排序顺序返回。"""
    stmt = (
        select(TripChecklist)
        .where(TripChecklist.trip_id == trip_id)
        .order_by(TripChecklist.category, TripChecklist.sort_order, TripChecklist.id)
    )
    return list(db.scalars(stmt).all())


def create_checklist_item(db: Session, trip_id: int, category: str, content: str, sort_order: int = 0) -> TripChecklist:
    item = TripChecklist(trip_id=trip_id, category=category, content=content, sort_order=sort_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_checklist_item(db: Session, item_id: int, content: str | None = None, is_checked: bool | None = None, category: str | None = None) -> TripChecklist | None:
    item = db.get(TripChecklist, item_id)
    if not item:
        return None
    if content is not None:
        item.content = content
    if is_checked is not None:
        item.is_checked = is_checked
    if category is not None:
        item.category = category
    db.commit()
    db.refresh(item)
    return item


def delete_checklist_item(db: Session, item_id: int) -> bool:
    item = db.get(TripChecklist, item_id)
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def generate_checklist_with_ai(db: Session, trip: TripRecord, plan: TripPlan) -> list[TripChecklist]:
    """调用 AI 根据行程信息生成出行清单。

    生成失败时回退到 FALLBACK_CHECKLIST 通用模板。
    已有清单条目不会被覆盖,仅追加新条目。
    """
    from hello_agents import SimpleAgent

    preferences = ""
    if plan.days:
        attractions = []
        for day in plan.days[:2]:
            attractions.extend(a.name for a in day.attractions[:2])
        preferences = "、".join(attractions[:4])

    prompt = CHECKLIST_PROMPT.format(
        city=plan.city,
        days=len(plan.days),
        transportation=plan.days[0].transportation if plan.days else "未知",
        accommodation=plan.days[0].accommodation if plan.days else "未知",
        preferences=preferences or "无",
        start_date=plan.start_date,
        end_date=plan.end_date,
    )

    try:
        agent = SimpleAgent(
            name="出行清单生成Agent",
            llm=get_llm(),
            system_prompt="请严格输出合法JSON数组。",
        )
        response = agent.run(prompt)
        match = re.search(r"\[[\s\S]*\]", response)
        if not match:
            raise ValueError("AI 未返回 JSON 数组")
        items_data = json.loads(match.group())
        if not isinstance(items_data, list) or not items_data:
            raise ValueError("AI 返回的清单为空")

        # 查询已有清单内容,避免重复
        existing_contents = {item.content for item in list_checklist(db, trip.id)}
        created: list[TripChecklist] = []
        sort_order = 0
        for entry in items_data:
            if not isinstance(entry, dict):
                continue
            category = entry.get("category", "其他")
            if category not in CATEGORIES:
                category = "其他"
            content = str(entry.get("content", "")).strip()
            if not content or content in existing_contents:
                continue
            item = create_checklist_item(db, trip.id, category, content, sort_order)
            created.append(item)
            existing_contents.add(content)
            sort_order += 1

        if not created:
            raise ValueError("AI 生成的清单全部已存在或为空")
        logger.info("checklist_ai_generated trip_id={} count={}", trip.id, len(created))
        return created
    except Exception as error:
        logger.warning("checklist_ai_failed trip_id={} error={}, using fallback", trip.id, str(error))
        existing_contents = {item.content for item in list_checklist(db, trip.id)}
        created: list[TripChecklist] = []
        sort_order = 0
        for category, content in FALLBACK_CHECKLIST:
            if content in existing_contents:
                continue
            item = create_checklist_item(db, trip.id, category, content, sort_order)
            created.append(item)
            sort_order += 1
        return created
