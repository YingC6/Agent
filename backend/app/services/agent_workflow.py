"""LangGraph 旅行规划工作流

状态机节点拓扑:

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
                                      END

条件路由由 _route_after_review 决定,保证审核-修正循环受 max_review_rounds 约束。
"""

from __future__ import annotations

import time
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from loguru import logger

from ..config import get_settings
from ..models.schemas import TripPlan, TripRequest


class TravelWorkflowState(TypedDict, total=False):
    """工作流状态。

    所有节点共享此状态,通过返回部分字典更新字段。
    emit 与 progress_callback 为运行时闭包,不参与持久化。
    """
    request: TripRequest
    knowledge_context: str
    progress_callback: Callable[[dict[str, Any]], None] | None
    emit: Callable[[str, str, str, float | None], None]
    planner: Any
    tool_results: dict[str, str]
    plan: TripPlan
    review_data: dict[str, Any]
    review_round: int
    max_rounds: int


def _make_emit(progress_callback: Callable[[dict[str, Any]], None] | None) -> Callable[[str, str, str, float | None], None]:
    """构造 emit 闭包,统一封装步骤事件并转发给前端 progress_callback。"""
    def emit(name: str, status: str, summary: str = "", started_at: float | None = None) -> None:
        step = {
            "name": name,
            "status": status,
            "summary": summary,
            "duration_ms": int((time.time() - started_at) * 1000) if started_at else 0,
        }
        if progress_callback:
            progress_callback(step)
    return emit


def _prepare_context(state: TravelWorkflowState) -> dict[str, Any]:
    """初始化节点:构造 emit 闭包,读取最大审核轮次配置。"""
    emit = _make_emit(state.get("progress_callback"))
    settings = get_settings()
    emit("LangGraph工作流", "success", "已完成需求、知识上下文和工具执行状态初始化")
    return {
        "emit": emit,
        "review_round": 0,
        "max_rounds": settings.max_review_rounds,
    }


def _research(state: TravelWorkflowState) -> dict[str, Any]:
    """节点1: 并行调用景点/天气/酒店 Agent 收集原始信息。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    tool_results = planner.research_phase(request, emit)
    return {"tool_results": tool_results}


def _generate(state: TravelWorkflowState) -> dict[str, Any]:
    """节点2: 调用规划 Agent 生成结构化行程。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    tool_results = state.get("tool_results", {})
    knowledge_context = state.get("knowledge_context", "")
    plan = planner.generate_phase(request, tool_results, knowledge_context, emit)
    return {"plan": plan}


def _review(state: TravelWorkflowState) -> dict[str, Any]:
    """节点3: 调用审核 Agent 检查行程合理性。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    plan = state["plan"]
    round_index = state.get("review_round", 0)
    review_data = planner.review_phase(plan, request, round_index, emit)
    return {"review_data": review_data}


def _optimize(state: TravelWorkflowState) -> dict[str, Any]:
    """节点4: 根据审核意见调用修正 Agent 优化行程。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    plan = state["plan"]
    review_data = state.get("review_data", {})
    round_index = state.get("review_round", 0)
    optimized_plan = planner.optimize_phase(plan, review_data, request, round_index, emit)
    return {"plan": optimized_plan, "review_round": round_index + 1}


def _enrich(state: TravelWorkflowState) -> dict[str, Any]:
    """节点5: 补充真实通勤时长、舒适度与备选方案。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    plan = state["plan"]
    enriched_plan = planner.enrich_phase(plan, request, emit)
    return {"plan": enriched_plan}


def _route_after_review(state: TravelWorkflowState) -> str:
    """条件路由:审核通过或达到最大轮次时进入 enrich,否则进入 optimize。"""
    review_data = state.get("review_data", {})
    review_round = state.get("review_round", 0)
    max_rounds = state.get("max_rounds", 1)

    if review_data.get("passed", False):
        logger.info("workflow_route review=passed round={} next=enrich", review_round)
        return "enrich"

    if review_round >= max_rounds:
        logger.info("workflow_route review=failed round={} max={} next=enrich", review_round, max_rounds)
        plan = state.get("plan")
        if plan is not None:
            plan.overall_suggestions = (
                f"{plan.overall_suggestions}\n系统已完成{max_rounds + 1}轮审核，建议出行前再次确认景点开放时间、路线和预算。"
            )
        return "enrich"

    logger.info("workflow_route review=failed round={} next=optimize", review_round)
    return "optimize"


def _build_travel_graph() -> Any:
    """构建并编译 LangGraph 状态图。"""
    graph = StateGraph(TravelWorkflowState)
    graph.add_node("prepare_context", _prepare_context)
    graph.add_node("research", _research)
    graph.add_node("generate", _generate)
    graph.add_node("review", _review)
    graph.add_node("optimize", _optimize)
    graph.add_node("enrich", _enrich)

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "research")
    graph.add_edge("research", "generate")
    graph.add_edge("generate", "review")
    graph.add_conditional_edges(
        "review",
        _route_after_review,
        {"enrich": "enrich", "optimize": "optimize"},
    )
    graph.add_edge("optimize", "review")
    graph.add_edge("enrich", END)
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

    graph = _get_travel_graph()
    initial_state: TravelWorkflowState = {
        "request": request,
        "knowledge_context": knowledge_context,
        "progress_callback": progress_callback,
        "planner": planner,
    }
    final_state = graph.invoke(initial_state)
    return final_state["plan"]
