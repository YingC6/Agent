"""对话摘要记忆服务

当未摘要对话的规模超过阈值时,自动把较早的消息滚动合并进摘要,避免上下文窗口溢出。

工作原理:
1. 每次发送消息后估算未摘要部分的 token(字符近似)
2. 若未摘要部分超过 SUMMARY_TOKEN_THRESHOLD,则将最早的一批消息交给 LLM
3. LLM 把「已有摘要 + 新增对话」合并成一段新摘要,直接覆盖旧摘要(而不是无限追加)
4. summarized_message_count 推进到已摘要位置,context_builder 只取之后的最近消息

这样即使对话持续数百轮,摘要长度也保持稳定,关键信息不丢失。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from ..agents.registry import get_agent
from .context_builder import estimate_tokens

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ..models.db_models import Conversation

# 触发摘要的未摘要 token 阈值(按字符近似计算)
SUMMARY_TOKEN_THRESHOLD = 1200
# 每次摘要保留的最近消息数(不参与摘要)
KEEP_RECENT_COUNT = 6
# 摘要最大长度,防止合并后无限膨胀
SUMMARY_MAX_CHARS = 800
# 摘要提示词
SUMMARY_PROMPT = """你是旅行对话摘要助手。请把「已有摘要」和「待摘要对话」滚动合并为一段新的简洁摘要,保留:
1. 用户已确认的行程调整(如换了哪些景点、改了哪天安排)
2. 用户的明确偏好和约束(如预算、餐饮要求、避免的地点)
3. 助手给出的关键建议
规则:新信息覆盖旧信息,只输出合并后的摘要正文,不要列表编号,控制在200字以内。

已有摘要:{existing_summary}

待摘要对话:
{dialog_text}"""


def maybe_summarize_conversation(db: "Session", conversation: "Conversation") -> bool:
    """检查并按需生成对话摘要。

    Returns:
        是否生成了新摘要
    """
    messages = list(conversation.messages)
    total_count = len(messages)
    summarized_count = conversation.summarized_message_count or 0
    if total_count - summarized_count <= KEEP_RECENT_COUNT:
        return False

    unsummarized_text = "\n".join(message.content for message in messages[summarized_count:])
    if estimate_tokens(unsummarized_text) <= SUMMARY_TOKEN_THRESHOLD:
        return False

    # 确定待摘要范围:从 summarized_count 到 total_count - KEEP_RECENT_COUNT
    end_index = total_count - KEEP_RECENT_COUNT
    if end_index <= summarized_count:
        return False

    to_summarize = messages[summarized_count:end_index]
    if not to_summarize:
        return False

    dialog_text = "\n".join(f"{msg.role}: {msg.content[:300]}" for msg in to_summarize)
    existing_summary = conversation.summary or ""

    prompt = SUMMARY_PROMPT.format(existing_summary=existing_summary or "无", dialog_text=dialog_text)

    started_at = time.monotonic()
    try:
        new_summary = get_agent(
            "conversation_summary",
            "对话摘要Agent",
            "请用中文输出简洁的对话摘要。",
        ).run(prompt).strip()
        if not new_summary:
            return False

        # 滚动合并:LLM 已把旧摘要与新增对话合并,这里直接覆盖并限制总长度
        conversation.summary = new_summary[:SUMMARY_MAX_CHARS]
        conversation.summarized_message_count = end_index
        db.commit()
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "conversation_summary conversation_id={} summarized={} total={} summary_chars={} duration_ms={}",
            conversation.id,
            len(to_summarize),
            total_count,
            len(conversation.summary),
            duration_ms,
        )
        return True
    except Exception as error:
        logger.warning("conversation_summary_failed conversation_id={} error={}", conversation.id, str(error))
        return False
