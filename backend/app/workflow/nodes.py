"""工作流节点实现。

节点只做接线:调用 planner/服务提供的能力,并把结果写入 state。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..config import get_settings
from ..domain.validators.execution import merge_validation_warnings, validate_plan_execution
from .emit import StepEmitter
from .state import TravelWorkflowState


def prepare_context(state: TravelWorkflowState) -> dict[str, Any]:
    """初始化节点:构造 emit 闭包,读取最大审核轮次配置。"""
    run_id = state["run_id"]
    emit = StepEmitter(state.get("progress_callback"), run_id)
    emit("LangGraph工作流", "success", "已完成需求、知识上下文和工具执行状态初始化")
    return {
        "emit": emit,
        "review_round": 0,
        "max_rounds": get_settings().max_review_rounds,
    }


def research(state: TravelWorkflowState) -> dict[str, Any]:
    """节点1: 并行调用景点/天气/酒店 Agent 收集调研证据。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    memory_context = state.get("memory_context", "")
    return {"research": planner.research_phase(request, emit, memory_context=memory_context)}


def generate(state: TravelWorkflowState) -> dict[str, Any]:
    """节点2: 调用规划 Agent 生成结构化行程。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    research = state.get("research")
    knowledge_context = state.get("knowledge_context", "")
    memory_context = state.get("memory_context", "")
    plan = planner.generate_phase(request, research, knowledge_context, emit, memory_context=memory_context)
    return {"plan": plan}


def review(state: TravelWorkflowState) -> dict[str, Any]:
    """节点3: 调用审核 Agent 检查行程合理性。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    plan = state["plan"]
    round_index = state.get("review_round", 0)
    memory_context = state.get("memory_context", "")
    return {"review_data": planner.review_phase(plan, request, round_index, emit, memory_context=memory_context)}


def optimize(state: TravelWorkflowState) -> dict[str, Any]:
    """节点4: 根据审核意见调用修正 Agent 优化行程。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    plan = state["plan"]
    review_data = state.get("review_data", {})
    round_index = state.get("review_round", 0)
    memory_context = state.get("memory_context", "")
    return {
        "plan": planner.optimize_phase(plan, review_data, request, round_index, emit, memory_context=memory_context),
        "review_round": round_index + 1,
    }


def enrich(state: TravelWorkflowState) -> dict[str, Any]:
    """节点5: 补充真实通勤时长、舒适度与备选方案。"""
    planner = state["planner"]
    emit = state["emit"]
    request = state["request"]
    plan = state["plan"]
    return {"plan": planner.enrich_phase(plan, request, emit)}


def validate_execution(state: TravelWorkflowState) -> dict[str, Any]:
    """节点6: 以确定性规则验证行程数据与可执行性。"""
    emit = state["emit"]
    plan = state["plan"]
    request = state["request"]
    result = validate_plan_execution(plan, request)
    if result.errors:
        emit("确定性行程校验", "failed", "；".join(result.errors[:3]))
        raise ValueError("；".join(result.errors))
    if result.warnings:
        plan = merge_validation_warnings(plan, result)
    emit(
        "确定性行程校验",
        "success",
        "；".join(result.warnings[:3]) if result.warnings else "城市、日期、景点、预算和通勤规则校验通过",
    )
    return {"plan": plan}


def route_after_review(state: TravelWorkflowState) -> str:
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
