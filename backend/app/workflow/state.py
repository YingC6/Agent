"""LangGraph 工作流状态定义。

所有节点共享此状态,通过返回部分字典更新字段。
节点间只传递类型化契约(research: ResearchBundle),不传递 LLM 原始文本集合。
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from ..domain.contracts import ResearchBundle
from ..models.schemas import TripPlan, TripRequest


class TravelWorkflowState(TypedDict, total=False):
    """工作流状态。

    emit 与 progress_callback 为运行时闭包,不参与持久化。
    """
    request: TripRequest
    knowledge_context: str
    progress_callback: Callable[[dict[str, Any]], None] | None
    emit: Callable[[str, str, str, float | None], None]
    planner: Any
    research: ResearchBundle
    plan: TripPlan
    review_data: dict[str, Any]
    review_round: int
    max_rounds: int
    run_id: str
    memory_context: str
