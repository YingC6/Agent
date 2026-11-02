"""行程修正服务。

收敛两条修正路径的解析与兜底逻辑,但保留各自的提示词与重试语义:
1. 审核驱动的修正:单次调用,解析失败即降级为备用行程。
2. 用户指令驱动的优化:最多两次尝试,并检测是否发生实质变化。
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from ..agents.parsers import extract_json, parse_json_object
from ..agents.prompts import OPTIMIZE_PROMPT
from ..agents.registry import get_agent
from ..agents.runtime import AgentRuntime
from ..domain.fallback import build_fallback_plan
from ..domain.scheduler import build_day_timeline
from ..models.schemas import TripPlan, TripRequest


def _extract_plan_data(data: dict[str, Any]) -> dict[str, Any]:
    """兼容 LLM 把行程嵌套在 plan 键中的返回结构。"""
    if isinstance(data, dict) and "plan" in data and isinstance(data["plan"], dict):
        return data["plan"]
    return data


def parse_plan_response(response: str, request: TripRequest) -> TripPlan:
    """解析规划/修正响应,失败时返回明确标记的备用行程。"""
    try:
        return TripPlan(**parse_json_object(response))
    except Exception as error:
        logger.warning("plan_parse_failed error={}", str(error))
        return build_fallback_plan(request, f"规划结果解析失败: {error}")


def revise_with_review(
    runtime: AgentRuntime,
    request: TripRequest,
    plan: TripPlan,
    review_data: dict[str, Any],
    memory_context: str = "",
) -> TripPlan:
    """审核驱动修正:单次调用修正 Agent,解析失败降级。"""
    payload: dict[str, Any] = {"request": request.model_dump(), "plan": plan.model_dump(), "review": review_data}
    if memory_context:
        payload["memory"] = memory_context
    query = json.dumps(payload, ensure_ascii=False)
    return parse_plan_response(runtime.run(query), request)


def optimize_with_instruction(plan: TripPlan, instruction: str) -> TripPlan:
    """用户指令驱动的优化:最多两次尝试,未产生实质变化时追加提醒重试。"""
    import time as _time

    plan_json = json.dumps({"plan": plan.model_dump(), "instruction": instruction}, ensure_ascii=False)
    last_error = "未知错误"
    runtime = get_agent("trip_optimizer", "行程优化Agent", OPTIMIZE_PROMPT)

    for attempt in range(2):
        try:
            response = runtime.run(plan_json)
            logger.info("optimize_response attempt=%d length=%d preview=%s", attempt, len(response), response[:200])
            data = _extract_plan_data(extract_json(response))
            new_plan = TripPlan(**data)
            # 时间表由确定性排程重建,避免沿用优化前的旧时间轴
            for day in new_plan.days:
                day.timeline = build_day_timeline(day)

            old_names = {a.name for day in plan.days for a in day.attractions}
            new_names = {a.name for day in new_plan.days for a in day.attractions}
            if old_names == new_names and new_plan.budget.total == plan.budget.total:
                logger.warning("optimize_no_change detected, instruction=%s", instruction[:100])
                if attempt == 0:
                    plan_json = json.dumps({
                        "plan": plan.model_dump(),
                        "instruction": f"请务必修改行程! {instruction}",
                        "reminder": "上次返回的行程与原行程完全相同,请根据要求做实质性调整",
                    }, ensure_ascii=False)
                    continue

            logger.info(
                "optimize_success attempt=%d attractions_old=%d attractions_new=%d",
                attempt,
                len(old_names),
                len(new_names),
            )
            return new_plan
        except Exception as error:
            last_error = str(error)
            logger.error("optimize_failed attempt=%d error=%s", attempt, last_error, exc_info=True)
            if attempt == 0:
                _time.sleep(1)
                continue

    logger.warning("optimize_fallback returning original plan with suggestion text")
    plan.overall_suggestions = f"{plan.overall_suggestions}\n⚠️ AI优化未能成功生成新方案(原因: {last_error[:100]})。手动建议: {instruction}"
    return plan
