"""LangGraph 旅行规划工作流。

状态机节点拓扑(与重构前保持一致):

    START
      ↓
    prepare_context  ── 初始化需求、知识库、emit 上下文
      ↓
    research         ── 并行调用景点/天气/酒店 Agent
      ↓
    generate         ── 规划 Agent 生成结构化行程
      ↓
    review           ── 审核 Agent 检查行程合理性
      ↓
    ┌── passed=true 或已达最大轮次 ──→ enrich
    │
    └── passed=false ──→ optimize ──→ review (循环)
                                       ↓
                                     enrich  ── 补充真实通勤/舒适度/备选方案
                                       ↓
                                 validate_execution
                                       ↓
                                      END

条件路由由 route_after_review 决定,保证审核-修正循环受 max_review_rounds 约束。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from loguru import logger

from ..models.schemas import TripPlan, TripRequest
from .nodes import (
    enrich,
    generate,
    optimize,
    prepare_context,
    research,
    review,
    route_after_review,
    validate_execution,
)
from .state import TravelWorkflowState


def _build_travel_graph() -> Any:
    """构建并编译 LangGraph 状态图。"""
    graph = StateGraph(TravelWorkflowState)
    graph.add_node("prepare_context", prepare_context)
    graph.add_node("research", research)
    graph.add_node("generate", generate)
    graph.add_node("review", review)
    graph.add_node("optimize", optimize)
    graph.add_node("enrich", enrich)
    graph.add_node("validate_execution", validate_execution)

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "research")
    graph.add_edge("research", "generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"enrich": "enrich", "optimize": "optimize"},
    )
    graph.add_edge("optimize", "review")
    graph.add_edge("enrich", "validate_execution")
    graph.add_edge("validate_execution", END)
    return graph.compile()


_TRAVEL_GRAPH = None


def _get_travel_graph() -> Any:
    """单例缓存编译后的工作流图,避免每次请求重复编译。"""
    global _TRAVEL_GRAPH
    if _TRAVEL_GRAPH is None:
        _TRAVEL_GRAPH = _build_travel_graph()
    return _TRAVEL_GRAPH


def run_travel_workflow(
    request: TripRequest,
    knowledge_context: str,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    planner: Any = None,
    run_id: str = "",
    memory_context: str = "",
) -> TripPlan:
    """运行 LangGraph 旅行规划工作流。

    Args:
        request: 旅行请求
        knowledge_context: 知识库检索上下文
        progress_callback: 步骤进度回调,用于向前端推送 SSE 事件
        planner: MultiAgentTripPlanner 实例,提供各阶段方法

    Returns:
        生成并增强后的旅行计划
    """
    if planner is None:
        raise ValueError("run_travel_workflow 需要 planner 实例以调用各阶段方法")

    resolved_run_id = run_id or uuid.uuid4().hex
    graph = _get_travel_graph()
    initial_state: TravelWorkflowState = {
        "request": request,
        "knowledge_context": knowledge_context,
        "progress_callback": progress_callback,
        "planner": planner,
        "run_id": resolved_run_id,
        "memory_context": memory_context,
    }
    logger.info("workflow_started run_id={} city={} travel_days={}", resolved_run_id, request.city, request.travel_days)
    try:
        final_state = graph.invoke(initial_state)
        plan = final_state["plan"]
        logger.info(
            "workflow_completed run_id={} source={} fallback={}",
            resolved_run_id,
            plan.source,
            plan.is_fallback,
        )
        return plan
    except Exception:
        logger.exception("workflow_failed run_id={}", resolved_run_id)
        raise
