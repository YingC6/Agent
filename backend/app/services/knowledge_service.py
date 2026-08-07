"""旅行知识库服务"""

import json
import re
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models.db_models import KnowledgeItem, TripRating, TripRecord
from ..models.schemas import TripPlan, TripRequest

SYNONYMS = {
    "美食": ["吃", "小吃", "火锅", "特色菜", "餐厅"],
    "休闲": ["轻松", "不赶", "慢节奏", "放松"],
    "历史文化": ["博物馆", "古城", "遗址", "寺庙"],
    "自然风光": ["山", "湖", "公园", "徒步"],
    "亲子": ["孩子", "儿童", "家庭", "熊猫"]
}


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,，、]", value) if item.strip()]


def expand_terms(terms: list[str], text: str = "") -> set[str]:
    result = set(terms)
    for key, values in SYNONYMS.items():
        if key in result or any(value in text for value in values):
            result.add(key)
            result.update(values)
    for term in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text):
        result.add(term)
    return result


def parse_markdown(markdown: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    content = markdown.strip()
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            raw_meta = content[3:end].strip()
            content = content[end + 3:].strip()
            for line in raw_meta.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
    title = meta.get("title")
    if not title:
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = match.group(1).strip() if match else "未命名攻略"
    return {
        "title": title,
        "city": meta.get("city", ""),
        "days": int(meta["days"]) if str(meta.get("days", "")).isdigit() else None,
        "themes": meta.get("themes", ""),
        "keywords": meta.get("keywords", ""),
        "content": content
    }


def create_knowledge_item(db: Session, data: dict[str, Any], source: str = "markdown", source_ref_id: int | None = None, rating: int = 0, created_by: int | None = None) -> KnowledgeItem:
    item = KnowledgeItem(
        title=data.get("title", "未命名知识"),
        city=data.get("city", ""),
        days=data.get("days"),
        themes=data.get("themes", ""),
        keywords=data.get("keywords", ""),
        source=source,
        source_ref_id=source_ref_id,
        content=data.get("content", ""),
        rating=rating,
        created_by=created_by
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def import_markdown_knowledge(db: Session, markdown: str, created_by: int | None = None) -> KnowledgeItem:
    return create_knowledge_item(db, parse_markdown(markdown), created_by=created_by)


def score_knowledge(item: KnowledgeItem, request: TripRequest) -> int:
    score = 0
    request_text = request.free_text_input or ""
    request_terms = expand_terms(request.preferences, request_text)
    item_themes = set(split_csv(item.themes))
    item_keywords = set(split_csv(item.keywords))
    if item.city and item.city == request.city:
        score += 50
    if item.days:
        diff = abs(item.days - request.travel_days)
        if diff == 0:
            score += 20
        elif diff == 1:
            score += 10
    score += len(request_terms & item_themes) * 10
    score += len(request_terms & item_keywords) * 5
    score += min(item.rating, 5) * 3
    score += min(item.usage_count, 10)
    if request_text and any(keyword in request_text for keyword in item_keywords):
        score += 10
    return score


def search_relevant_knowledge(db: Session, request: TripRequest, limit: int = 3) -> list[KnowledgeItem]:
    items = db.scalars(select(KnowledgeItem)).all()
    scored = [(score_knowledge(item, request), item) for item in items]
    matched = [(score, item) for score, item in scored if score > 0]
    matched.sort(key=lambda pair: pair[0], reverse=True)
    result = [item for _, item in matched[:limit]]
    for item in result:
        item.usage_count += 1
    if result:
        db.commit()
    return result


def build_knowledge_context(items: list[KnowledgeItem]) -> str:
    if not items:
        return ""
    parts = []
    for index, item in enumerate(items, 1):
        parts.append(f"参考资料{index}: {item.title}\n城市: {item.city}\n主题: {item.themes}\n内容: {item.content[:600]}")
    return "\n\n".join(parts)


def knowledge_to_dict(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "city": item.city,
        "days": item.days,
        "themes": split_csv(item.themes),
        "keywords": split_csv(item.keywords),
        "source": item.source,
        "source_ref_id": item.source_ref_id,
        "content": item.content,
        "rating": item.rating,
        "usage_count": item.usage_count,
        "created_at": item.created_at.isoformat()
    }


def trip_to_knowledge_text(plan: TripPlan, comment: str = "") -> dict[str, Any]:
    attractions = []
    lines = []
    for day in plan.days:
        names = [attraction.name for attraction in day.attractions]
        attractions.extend(names)
        lines.append(f"第{day.day_index + 1}天: {'、'.join(names)}。{day.description}")
    return {
        "title": f"{plan.city}{len(plan.days)}日高评分行程",
        "city": plan.city,
        "days": len(plan.days),
        "themes": "",
        "keywords": "、".join(dict.fromkeys(attractions)),
        "content": "\n".join(lines) + (f"\n用户评价: {comment}" if comment else "")
    }


def rate_trip(db: Session, trip: TripRecord, user_id: int, rating: int, comment: str = "") -> TripRating:
    exists = db.scalars(select(TripRating).where(TripRating.trip_id == trip.id, TripRating.user_id == user_id)).first()
    if exists:
        exists.rating = rating
        exists.comment = comment
        record = exists
    else:
        record = TripRating(trip_id=trip.id, user_id=user_id, rating=rating, comment=comment)
        db.add(record)
    db.commit()
    db.refresh(record)
    old = db.scalars(select(KnowledgeItem).where(KnowledgeItem.source == "rated_trip", KnowledgeItem.source_ref_id == trip.id)).first()
    if rating >= 4:
        plan = TripPlan(**json.loads(trip.plan_json))
        data = trip_to_knowledge_text(plan, comment)
        if old:
            old.title = data["title"]
            old.city = data["city"]
            old.days = data["days"]
            old.keywords = data["keywords"]
            old.content = data["content"]
            old.rating = rating
            db.commit()
        else:
            create_knowledge_item(db, data, source="rated_trip", source_ref_id=trip.id, rating=rating, created_by=user_id)
    elif old:
        db.delete(old)
        db.commit()
    return record
