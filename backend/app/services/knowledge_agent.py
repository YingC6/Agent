"""Agentic RAG 检索编排

把知识检索从固定的一次调用升级为可自适应的循环:
1. 检索一轮(规则评分 +向量召回)
2. 确定性判断召回是否充分
3. 不充分且未达轮数上限时,由 LLM 改写查询后重检
4. 命中分块与轮次轨迹一并返回,供上层记录与溯源

成本控制:
- 充分性判断完全确定性,不额外调用 LLM
- 只有召回不足时才触发查询改写,正常情况一轮结束
- 硬上限 MAX_ROUNDS,避免无限循环
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger
from sqlalchemy.orm import Session

from ..models.schemas import TripRequest
from .knowledge_service import (
    KnowledgeHit,
    build_knowledge_context,
    build_retrieval_query,
    retrieve_knowledge,
)

# 检索循环硬上限,与审核 Agent 的迭代约束一致
MAX_ROUNDS = 2
# 最高匹配分达到该值即认为召回充分
SUFFICIENT_SCORE = 50.0
# 上下文达到该长度即认为召回充分
SUFFICIENT_CONTEXT_CHARS = 240


@dataclass
class RetrievalTrace:
    """单轮检索轨迹。"""
    round: int
    query: str
    hits: int
    top_score: float
    sufficient: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "query": self.query,
            "hits": self.hits,
            "top_score": round(self.top_score, 2),
            "sufficient": self.sufficient,
            "reason": self.reason,
        }


@dataclass
class AgenticRetrievalResult:
    """Agentic 检索结果。"""
    hits: list[KnowledgeHit] = field(default_factory=list)
    context: str = ""
    rounds: int = 0
    traces: list[RetrievalTrace] = field(default_factory=list)

    def refs(self) -> list[dict[str, Any]]:
        """知识溯源:记录本次实际采用了哪些资料。"""
        return [
            {
                "id": hit.item.id,
                "title": hit.item.title,
                "city": hit.item.city,
                "score": round(hit.score, 2),
                "source": hit.source,
                "chunk_index": hit.chunk.index if hit.chunk else None,
            }
            for hit in self.hits
        ]


def _judge_sufficiency(hits: list[KnowledgeHit], context: str) -> tuple[bool, str]:
    """确定性判断召回是否充分,不消耗 LLM 调用。"""
    if not hits:
        return False, "未召回任何知识条目"
    top_score = max(hit.score for hit in hits)
    if top_score >= SUFFICIENT_SCORE:
        return True, f"最高匹配分 {top_score:.1f} 达到阈值 {SUFFICIENT_SCORE:.0f}"
    if len(context) >= SUFFICIENT_CONTEXT_CHARS:
        return True, f"上下文 {len(context)} 字符达到阈值 {SUFFICIENT_CONTEXT_CHARS}"
    return False, f"最高匹配分仅 {top_score:.1f},上下文 {len(context)} 字符不足"


def _rewrite_query(request: TripRequest, base_query: str, gap_reason: str) -> str:
    """召回不足时改写检索查询,失败则回退到结构化查询。"""
    from hello_agents import SimpleAgent

    from .llm_service import get_llm

    prompt = f"""你是旅行知识检索的查询改写器。当前检索结果不足:{gap_reason}
请把下面的旅行需求改写为一条更适合知识库检索的中文查询,突出城市、天数、游玩主题和用户明确需求,可以补充同类场景词。
要求:只输出一行查询文本,不超过60字,不要解释,不要加引号。
原始需求:{base_query}"""
    try:
        response = SimpleAgent(
            name="检索查询改写Agent",
            llm=get_llm(),
            system_prompt="只输出一行中文检索查询,不要任何解释。",
        ).run(prompt)
        text = (response or "").strip().splitlines()[0].strip().strip('"') if (response or "").strip() else ""
        if text:
            return text[:80]
    except Exception as error:
        logger.warning("knowledge_agent rewrite failed: {}", str(error))

    fallback = base_query
    if request.preferences:
        fallback += "；游玩主题：" + "、".join(request.preferences)
    if request.free_text_input:
        fallback += "；额外需求：" + request.free_text_input
    return fallback[:120]


def run_agentic_retrieval(
    db: Session,
    request: TripRequest,
    progress: Callable[[dict], None] | None = None,
    limit: int = 3,
    max_rounds: int = MAX_ROUNDS,
    rerank: bool = True,
) -> AgenticRetrievalResult:
    """执行 Agentic 检索循环,返回命中分块、上下文与轮次轨迹。"""
    result = AgenticRetrievalResult()
    base_query = build_retrieval_query(request)
    query: str | None = None
    seen: dict[int, KnowledgeHit] = {}
    merged: list[KnowledgeHit] = []
    context = ""

    for round_index in range(1, max_rounds + 1):
        round_started = time.time()
        hits = retrieve_knowledge(db, request, limit=limit, query=query, rerank=rerank)
        for hit in hits:
            current = seen.get(hit.item.id)
            if current is None or hit.score > current.score:
                seen[hit.item.id] = hit

        merged = sorted(seen.values(), key=lambda hit: hit.score, reverse=True)[:limit]
        context = build_knowledge_context(merged)
        sufficient, reason = _judge_sufficiency(merged, context)
        result.traces.append(
            RetrievalTrace(
                round=round_index,
                query=query or base_query,
                hits=len(merged),
                top_score=max((hit.score for hit in merged), default=0.0),
                sufficient=sufficient,
                reason=reason,
            )
        )
        result.rounds = round_index

        if progress:
            progress({
                "name": "知识库检索",
                "status": "success",
                "summary": f"第{round_index}轮召回{len(merged)}条知识,{reason}",
                "duration_ms": int((time.time() - round_started) * 1000),
            })

        if sufficient or round_index >= max_rounds:
            break

        query = _rewrite_query(request, base_query, reason)
        if progress:
            progress({
                "name": "检索查询改写",
                "status": "success",
                "summary": f"召回不足,改写查询为:{query}",
                "duration_ms": 0,
            })

    result.hits = merged
    result.context = context
    logger.info(
        "knowledge_agent done: rounds={} hits={} sources={}",
        result.rounds,
        len(result.hits),
        [trace.to_dict() for trace in result.traces],
    )
    return result
