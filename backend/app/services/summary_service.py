"""对话摘要记忆服务

当对话消息数量超过阈值时,自动将较早的消息摘要化,避免上下文窗口溢出。

工作原理:
1. 每次发送消息后检查对话总消息数
2. 若未摘要的消息数 > SUMMARY_THRESHOLD,则将最早的一批消息摘要
3. 摘要写入 conversation.summary,summarized_message_count 更新
4. context_builder 使用 summary + 最近 N 条消息构建上下文

这样即使对话持续数百轮,上下文也能保持简洁且信息不丢失。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from ..services.llm_service import get_llm

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ..models.db_models import Conversation

# 触发摘要的未摘要消息数阈值
SUMMARY_THRESHOLD = 10
# 每次摘要保留的最近消息数(不参与摘要)
KEEP_RECENT_COUNT = 6
# 摘要提示词
SUMMARY_PROMPT = """你是旅行对话摘要助手。请将以下对话历史浓缩为一段简洁的摘要,保留:
1. 用户已确认的行程调整(如换了哪些景点、改了哪天安排)
2. 用户的明确偏好和约束(如预算、餐饮要求、避免的地点)
3. 助手给出的关键建议
只输出摘要正文,不要列表编号,控制在200字以内。

已有摘要:{existing_summary}

待摘要对话:
{dialog_text}"""


def maybe_summarize_conversation(db: "Session", conversation: "Conversation") -> bool:
    """检查并按需生成对话摘要。

    Returns:
        是否生成了新摘要
    """
    from hello_agents import SimpleAgent

    messages = list(conversation.messages)
    total_count = len(messages)
    summarized_count = conversation.summarized_message_count or 0
    unsummarized_count = total_count - summarized_count

    if unsummarized_count <= SUMMARY_THRESHOLD:
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
        agent = SimpleAgent(
            name="对话摘要Agent",
            llm=get_llm(),
            system_prompt="请用中文输出简洁的对话摘要。",
        )
        new_summary = agent.run(prompt).strip()
        if not new_summary:
            return False

        # 如果已有旧摘要,将新摘要追加合并
        if existing_summary:
            conversation.summary = f"{existing_summary}\n{new_summary}"
        else:
            conversation.summary = new_summary

        conversation.summarized_message_count = end_index
        db.commit()
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "conversation_summary conversation_id={} summarized={} total={} duration_ms={}",
            conversation.id,
            len(to_summarize),
            total_count,
            duration_ms,
        )
        return True
    except Exception as error:
        logger.warning("conversation_summary_failed conversation_id={} error={}", conversation.id, str(error))
        return False
