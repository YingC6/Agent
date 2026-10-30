"""旅行知识库服务"""

import json
import re
from dataclasses import dataclass
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models.db_models import KnowledgeItem, TripRating, TripRecord
from ..models.schemas import TripPlan, TripRequest
from ..services.llm_service import get_llm
from hello_agents import SimpleAgent

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


@dataclass(frozen=True)
class KnowledgeChunk:
    item: KnowledgeItem
    index: int
    content: str


def split_knowledge_chunks(item: KnowledgeItem, chunk_size: int = 480, chunk_overlap: int = 80) -> list[KnowledgeChunk]:
    content = item.content.strip()
    if not content:
        return []
    chunks = []
    start = 0
    index = 0
    while start < len(content):
        end = min(len(content), start + chunk_size)
        if end < len(content):
            boundary = max(content.rfind("。", start, end), content.rfind("\n", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunks.append(KnowledgeChunk(item=item, index=index, content=content[start:end]))
        if end >= len(content):
            break
        start = max(end - chunk_overlap, start + 1)
        index += 1
    return chunks


@dataclass(frozen=True)
class KnowledgeHit:
    """一条检索命中:知识条目 + 实际命中的分块 + 综合得分 + 召回来源。"""
    item: KnowledgeItem
    chunk: KnowledgeChunk | None
    score: float
    source: str


def build_retrieval_query(request: TripRequest) -> str:
    preferences = "、".join(request.preferences) if request.preferences else "无"
    return f"目的地：{request.city}；天数：{request.travel_days}；偏好：{preferences}；补充需求：{request.free_text_input or '无'}"


def rerank_knowledge_with_llm(request: TripRequest, candidates: list[KnowledgeItem], limit: int) -> list[KnowledgeItem]:
    if not candidates:
        return []
    candidate_text = "\n".join(
        f"[{item.id}] 标题：{item.title}；城市：{item.city}；天数：{item.days or '未知'}；主题：{item.themes or '无'}；关键词：{item.keywords or '无'}；内容摘要：{item.content[:260]}"
        for item in candidates
    )
    prompt = f"""你是旅行知识检索重排器。根据旅行请求，从候选资料中选择最有帮助的资料并排序。优先保证城市匹配，其次考虑天数、主题和用户明确需求。只返回JSON数组，元素为候选资料ID，不要解释，不要返回候选列表外的ID，最多返回{limit}个。
旅行请求：{build_retrieval_query(request)}
候选资料：
{candidate_text}"""
    try:
        response = SimpleAgent(name="旅行知识重排Agent", llm=get_llm(), system_prompt="请严格输出合法JSON数组。").run(prompt)
        match = re.search(r"\[[\s\S]*?\]", response)
        if not match:
            raise ValueError("模型未返回资料ID数组")
        ranked_ids = json.loads(match.group())
        by_id = {item.id: item for item in candidates}
        result = [by_id[item_id] for item_id in ranked_ids if isinstance(item_id, int) and item_id in by_id]
        return result[:limit] or candidates[:limit]
    except Exception:
        return candidates[:limit]


# 向量相似度折算为与规则分可比的综合分
VECTOR_WEIGHT = 30.0
# 向量相似度低于该值时保留规则召回挑出的分块
VECTOR_CHUNK_THRESHOLD = 0.45


def _pick_rule_chunk(item: KnowledgeItem, terms: set[str]) -> KnowledgeChunk | None:
    """规则召回时挑选与请求词重合度最高的分块,避免注入无关片段。"""
    chunks = split_knowledge_chunks(item)
    if not chunks:
        return None
    return max(chunks, key=lambda chunk: sum(1 for term in terms if term in chunk.content))


def retrieve_knowledge(
    db: Session,
    request: TripRequest,
    limit: int = 3,
    query: str | None = None,
    rerank: bool = True,
) -> list[KnowledgeHit]:
    """混合检索:规则评分 + FAISS 向量召回,直接返回命中分块。

    与旧实现的关键差异:命中的分块会原样传给上下文构建,不再按条目重新切分,
    保证注入 LLM 的片段就是打分命中的那一段。
    rerank=False 时跳过 LLM 重排,用于对话这类对延迟敏感的场景。
    """
    items = db.scalars(select(KnowledgeItem)).all()
    if not items:
        return []

    request_terms = expand_terms(request.preferences, request.free_text_input or "")
    hits: dict[int, KnowledgeHit] = {}

    # 阶段1: 规则评分召回(城市/天数/主题/关键词)
    scored = [(score_knowledge(item, request), item) for item in items]
    matched = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: pair[0], reverse=True)[:8]
    for rule_score, item in matched:
        hits[item.id] = KnowledgeHit(
            item=item,
            chunk=_pick_rule_chunk(item, request_terms),
            score=float(rule_score),
            source="rule",
        )

    # 阶段2: 向量召回补充语义候选,按条目合并取最高分分块
    for vector_score, chunk in _vector_recall(items, query or build_retrieval_query(request), top_k=8):
        existing = hits.get(chunk.item.id)
        combined = vector_score * VECTOR_WEIGHT + (existing.score if existing else 0.0)
        keep_rule_chunk = existing is not None and existing.chunk is not None and vector_score < VECTOR_CHUNK_THRESHOLD
        hits[chunk.item.id] = KnowledgeHit(
            item=existing.item if existing else chunk.item,
            chunk=existing.chunk if keep_rule_chunk else chunk,
            score=combined,
            source=f"{existing.source}+vector" if existing else "vector",
        )

    # 阶段3: LLM 语义重排
    candidates = sorted(hits.values(), key=lambda hit: hit.score, reverse=True)[:8]
    if not candidates:
        return []
    by_id = {hit.item.id: hit for hit in candidates}
    if rerank:
        reranked = rerank_knowledge_with_llm(request, [hit.item for hit in candidates], limit)
        result = [by_id[item.id] for item in reranked if item.id in by_id][:limit]
    else:
        result = candidates[:limit]
    for hit in result:
        hit.item.usage_count += 1
    if result:
        db.commit()
    return result


def _vector_recall(items: list[KnowledgeItem], query: str, top_k: int = 8) -> list[tuple[float, KnowledgeChunk]]:
    """FAISS 向量召回,返回(相似度, 命中分块)。嵌入服务不可用时返回空列表触发降级。"""
    from .vector_store import get_vector_store

    if not items:
        return []
    vector_store = get_vector_store()
    if vector_store.needs_rebuild(items) or not vector_store.is_ready:
        if not vector_store.build_index(items):
            return []
    return [(result.score, result.chunk) for result in vector_store.search(query, top_k=top_k)]


def search_relevant_knowledge(db: Session, request: TripRequest, limit: int = 3) -> list[KnowledgeItem]:
    """只要条目本体时使用的兼容入口(如后台知识库检索调试接口)。"""
    return [hit.item for hit in retrieve_knowledge(db, request, limit=limit)]


def build_knowledge_context(hits: list[KnowledgeHit]) -> str:
    """把命中分块拼成 LLM 上下文,带上来源与匹配分便于溯源。"""
    if not hits:
        return ""
    parts = []
    for hit in hits:
        content = hit.chunk.content if hit.chunk else hit.item.content[:480]
        parts.append(
            f"参考资料：{hit.item.title}（匹配分 {hit.score:.1f}，来源 {hit.source}）\n"
            f"城市：{hit.item.city}\n主题：{hit.item.themes or '无'}\n内容：{content}"
        )
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
