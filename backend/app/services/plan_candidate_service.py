"""条件触发行程择优。

默认只生成一份行程;当规则评分低于阈值时,才并行生成少量备选,
再经过一次结构化评审(summarize)选优。硬上限:1 轮生成 + 1 轮评审,
不做多轮辩论,避免成本与延迟失控。
"""

from __future__ import annotations

import json
from typing import Callable

from loguru import logger

from ..agents.capabilities.trip import PLANNER
from ..agents.parsers import extract_json
from ..agents.prompts import CANDIDATE_SUMMARY_PROMPT
from ..agents.registry import get_agent
from ..agents.runtime import AgentRuntime
from ..config import get_settings
from ..domain.scoring import score_plan
from ..models.schemas import TripPlan, TripRequest
from ..services.llm_service import get_llm
from ..services.revision_service import parse_plan_response
from ..workflow.fanout import ParallelTask, run_parallel

CANDIDATE_VIEW_HINT = "\n\n**备选视角:** 上一次方案不够理想,请换一组景点组合与更合理的路线,避免与原方案重复。"


def improve_plan_if_needed(
    request: TripRequest,
    plan: TripPlan,
    planner_query: str,
    emit: Callable[[str, str, str, float | None], None],
) -> TripPlan:
    """评分不足时触发备选生成与评审,否则原样返回。"""
    settings = get_settings()
    primary_score = score_plan(plan, request)
    emit("行程自评分", "success", f"当前行程规则评分 {primary_score} 分")

    if plan.is_fallback or primary_score >= settings.plan_candidate_min_score:
        return plan

    emit("候选行程生成", "running", "评分低于阈值,正在并行生成备选行程")
    tasks = [
        ParallelTask(
            key=f"candidate_{index}",
            name=f"备选行程{index + 1}",
            summary="正在生成不同景点组合的备选方案",
            run=_make_candidate_runner(planner_query),
        )
        for index in range(max(settings.plan_candidate_count, 1))
    ]
    outcomes = run_parallel(tasks, emit)

    candidates = [plan]
    for outcome in outcomes:
        if outcome.error:
            continue
        candidates.append(parse_plan_response(str(outcome.value), request))
    candidates = candidates[: 1 + max(settings.plan_candidate_count, 1)]
    scores = [score_plan(candidate, request) for candidate in candidates]
    emit("候选行程评分", "success", "；".join(f"候选{i}：{score}分" for i, score in enumerate(scores)))

    winner_index, reason = _judge_candidates(request, candidates, scores)
    winner = candidates[winner_index] if 0 <= winner_index < len(candidates) else candidates[int(scores.index(max(scores)))]
    emit("候选行程评选", "success", reason[:180] or f"选择候选{winner_index}")
    return winner


def _make_candidate_runner(planner_query: str) -> Callable[[], str]:
    """每次备选都使用独立 AgentRuntime,避免并行时共享会话历史。"""
    def run() -> str:
        runtime = AgentRuntime(name=PLANNER.name, system_prompt=PLANNER.prompt, llm=get_llm())
        return runtime.run(planner_query + CANDIDATE_VIEW_HINT)

    return run


def _judge_candidates(
    request: TripRequest,
    candidates: list[TripPlan],
    scores: list[int],
) -> tuple[int, str]:
    """一次结构化评审选优;模型失败则回退到规则最高分。"""
    try:
        payload = json.dumps(
            {
                "request": {
                    "city": request.city,
                    "travel_days": request.travel_days,
                    "preferences": request.preferences,
                },
                "candidates": [
                    {
                        "index": index,
                        "score": scores[index],
                        "attractions": [attraction.name for day in plan.days for attraction in day.attractions],
                        "budget_total": plan.budget.total if plan.budget else 0,
                    }
                    for index, plan in enumerate(candidates)
                ],
            },
            ensure_ascii=False,
        )
        data = extract_json(
            get_agent("plan_candidate_judge", "候选行程评审", CANDIDATE_SUMMARY_PROMPT).run(payload)
        )
        index = int(data.get("winner_index", 0))
        if 0 <= index < len(candidates):
            return index, str(data.get("reason", ""))
    except Exception as error:
        logger.warning("candidate_judge_failed error={}", str(error))

    best = int(max(range(len(scores)), key=lambda i: scores[i]))
    return best, f"评审模型不可用,按规则评分选择候选{best}"
