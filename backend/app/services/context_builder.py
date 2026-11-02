import json

from sqlalchemy.orm import Session

from ..models.db_models import Conversation
from ..models.schemas import TripPlan
from .memory_service import build_user_memory_context

RECENT_MESSAGE_LIMIT = 6
# 上下文总预算(按字符近似 token),超出后按 知识 → 行程 → 历史 的顺序裁剪
MAX_CONTEXT_CHARS = 3600
SUMMARY_MAX_CHARS = 800
PREFERENCES_MAX_CHARS = 300
RECENT_HISTORY_MAX_CHARS = 900
PLAN_MAX_CHARS = 1400
PLAN_MIN_CHARS = 300
MAX_KNOWLEDGE_CONTEXT_CHARS = 2200


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数:中文场景按 1 字≈1 token 保守计算。"""
    return len(text)


def _recent_messages(conversation: Conversation) -> list:
    """取已摘要范围之后的最近若干条原始消息。"""
    summarized_count = conversation.summarized_message_count or 0
    all_messages = list(conversation.messages)
    recent = all_messages[summarized_count:][-RECENT_MESSAGE_LIMIT:]
    if not recent:
        recent = all_messages[-RECENT_MESSAGE_LIMIT:]
    return recent


def _history_text(messages: list, max_chars: int) -> str:
    """从最新一条往前收集,超出预算时丢弃更早的消息。"""
    lines: list[str] = []
    used = 0
    for message in reversed(messages):
        line = f"{message.role}: {message.content}"
        if used + len(line) > max_chars and lines:
            break
        lines.append(line[:max_chars - used])
        used += len(line)
    return "\n".join(reversed(lines))


def _plan_projection(plan: TripPlan, detailed: bool = True) -> dict:
    """把完整行程压缩为紧凑投影,只保留对话需要的字段,避免整份 JSON 占满上下文。"""
    days = []
    for day in plan.days:
        item = {
            "date": day.date,
            "theme": day.description[:40],
            "transportation": day.transportation,
            "attractions": [attraction.name for attraction in day.attractions],
        }
        if detailed:
            item["meals"] = [f"{meal.type}:{meal.name}" for meal in day.meals]
            item["hotel"] = day.hotel.name if day.hotel else day.accommodation
            item["route_segments"] = [f"{segment.origin}→{segment.destination}({segment.duration_minutes}分钟)" for segment in day.route_segments]
        else:
            item["attractions"] = item["attractions"][:4]
            item["meals"] = [meal.name for meal in day.meals][:3]
        days.append(item)
    return {
        "city": plan.city,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "days": days,
        "budget": plan.budget.model_dump() if plan.budget else None,
    }


def _plan_text(plan: TripPlan, max_chars: int) -> str:
    text = json.dumps(_plan_projection(plan), ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    compact = json.dumps(_plan_projection(plan, detailed=False), ensure_ascii=False)
    return compact[:max_chars]


def build_conversation_context(conversation: Conversation, plan: TripPlan, knowledge_context: str = "", db: Session | None = None) -> str:
    """构建对话上下文,包含历史摘要 + 最近消息 + 用户偏好 + 行程投影 + 知识库。

    预算分配(优先级从高到低):
    1. 历史摘要 / 最近消息 / 用户偏好:先按各自上限截断
    2. 当前行程:使用紧凑投影,最多占剩余预算的一半
    3. 知识库参考:最后分配剩余预算,不足时直接丢弃
    """
    summary = (conversation.summary or "").strip()[:SUMMARY_MAX_CHARS]
    history = _history_text(_recent_messages(conversation), RECENT_HISTORY_MAX_CHARS)
    preferences = (build_user_memory_context(db, conversation.user_id) if db else "")[:PREFERENCES_MAX_CHARS]

    remaining = MAX_CONTEXT_CHARS - len(summary) - len(history) - len(preferences)
    plan_budget = min(PLAN_MAX_CHARS, max(PLAN_MIN_CHARS, remaining // 2))
    plan_text = _plan_text(plan, plan_budget)
    knowledge_budget = remaining - len(plan_text)
    knowledge_text = knowledge_context.strip()[:max(0, min(MAX_KNOWLEDGE_CONTEXT_CHARS, knowledge_budget))]

    payload = {
        "priority": ["latest_user_request", "current_trip_version", "user_preferences", "conversation_summary", "retrieved_knowledge"],
        "current_plan": plan_text,
        "user_preferences": preferences,
        "conversation_summary": summary,
        "recent_messages": history,
        "retrieved_knowledge": knowledge_text,
    }
    return json.dumps(payload, ensure_ascii=False)
