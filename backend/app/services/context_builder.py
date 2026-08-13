import json

from sqlalchemy.orm import Session

from ..models.db_models import Conversation
from ..models.schemas import TripPlan
from .memory_service import build_user_memory_context


RECENT_MESSAGE_LIMIT = 6
MAX_KNOWLEDGE_CONTEXT_CHARS = 2200


def build_conversation_context(conversation: Conversation, plan: TripPlan, knowledge_context: str = "", db: Session | None = None) -> str:
    """构建对话上下文,包含历史摘要 + 最近消息 + 用户偏好 + 知识库。

    上下文层次(按优先级):
    1. 历史对话摘要:将较早的对话压缩为摘要,保留关键决策和偏好
    2. 最近消息:最近 RECENT_MESSAGE_LIMIT 条原始消息,保证细节不丢
    3. 当前行程版本:最新行程计划 JSON
    4. 用户长期偏好:从 UserMemory 表提取的偏好记忆
    5. 知识库参考:RAG 检索结果
    """
    # 优先使用已摘要后的最近消息,避免重复包含已摘要的内容
    summarized_count = conversation.summarized_message_count or 0
    all_messages = list(conversation.messages)
    recent_messages = all_messages[summarized_count:][-RECENT_MESSAGE_LIMIT:]
    if not recent_messages:
        recent_messages = all_messages[-RECENT_MESSAGE_LIMIT:]
    history = "\n".join(f"{message.role}: {message.content}" for message in recent_messages)

    summary = conversation.summary or ""
    payload = {
        "priority": ["latest_user_request", "current_trip_version", "user_preferences", "conversation_summary", "retrieved_knowledge"],
        "current_plan": plan.model_dump(),
        "user_preferences": build_user_memory_context(db, conversation.user_id) if db else "",
        "conversation_summary": summary[:800] if summary else "",
        "recent_messages": history,
        "retrieved_knowledge": knowledge_context[:MAX_KNOWLEDGE_CONTEXT_CHARS],
    }
    return json.dumps(payload, ensure_ascii=False)
