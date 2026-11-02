"""多智能体旅行规划系统(装配层)。

只负责装配智能体团队与串联各阶段;提示词、解析、校验、兜底均已下沉到
对应分层,避免再次膨胀为上帝类。
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from ..agents.capabilities.research import ResearchTeam
from ..agents.capabilities.trip import OPTIMIZER, PLANNER, REVIEW
from ..agents.parsers import parse_json_object
from ..agents.prompts import build_planner_query
from ..agents.runtime import AgentRuntime
from ..config import get_settings
from ..domain.clarification import detect_clarification
from ..domain.contracts import ResearchBundle
from ..domain.fallback import build_fallback_plan
from ..models.schemas import TripPlan, TripRequest
from ..services.itinerary_service import enrich_plan_execution_data
from ..services.llm_service import get_llm
from ..services.plan_candidate_service import improve_plan_if_needed
from ..services.revision_service import parse_plan_response, revise_with_review
from ..workflow.emit import StepEmitter
from ..workflow.graph import run_travel_workflow


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""

    def __init__(self):
        """初始化多智能体系统"""
        print("🔄 开始初始化多智能体旅行规划系统...")

        try:
            settings = get_settings()
            self.llm = get_llm()

            print("  - 创建MCP工具与并行调研小组...")
            env_vars = {"AMAP_MAPS_API_KEY": settings.amap_api_key}
            if settings.amap_security_key:
                env_vars["AMAP_SECURITY_KEY"] = settings.amap_security_key
            self.research_team = ResearchTeam(env_vars)

            print("  - 创建行程规划Agent...")
            self.planner_agent = AgentRuntime(name=PLANNER.name, system_prompt=PLANNER.prompt, llm=self.llm)

            print("  - 创建行程审核Agent...")
            self.review_agent = AgentRuntime(name=REVIEW.name, system_prompt=REVIEW.prompt, llm=self.llm)

            print("  - 创建行程修正Agent...")
            self.optimizer_agent = AgentRuntime(name=OPTIMIZER.name, system_prompt=OPTIMIZER.prompt, llm=self.llm)

            print("✅ 多智能体系统初始化成功")
            print(f"   景点搜索Agent: {len(self.research_team.attraction_agent.list_tools())} 个工具")
            print(f"   天气查询Agent: {len(self.research_team.weather_agent.list_tools())} 个工具")
            print(f"   酒店推荐Agent: {len(self.research_team.hotel_agent.list_tools())} 个工具")

        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def plan_trip(
        self,
        request: TripRequest,
        progress_callback: Callable[[dict], None] | None = None,
        knowledge_context: str = "",
        run_id: str = "",
        memory_context: str = "",
    ) -> TripPlan:
        """使用多智能体协作生成旅行计划。"""
        emit = StepEmitter(progress_callback, run_id)

        try:
            questions = detect_clarification(request)
            if questions:
                emit("需求澄清", "success", "；".join(questions))

            print(f"\n{'=' * 60}")
            print("🚀 开始多智能体协作规划旅行(LangGraph 工作流)...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            print(f"{'=' * 60}\n")

            trip_plan = run_travel_workflow(
                request=request,
                knowledge_context=knowledge_context,
                progress_callback=progress_callback,
                planner=self,
                run_id=run_id,
                memory_context=memory_context,
            )
            trip_plan.clarification_questions = questions

            print(f"{'=' * 60}")
            print("✅ 旅行计划生成完成!")
            print(f"{'=' * 60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            emit("异常兜底", "failed", str(e))
            return build_fallback_plan(request, str(e))

    # ============ LangGraph 工作流阶段方法 ============

    def research_phase(
        self,
        request: TripRequest,
        emit: Callable[[str, str, str, float | None], None],
        memory_context: str = "",
    ) -> ResearchBundle:
        """阶段1: 并行调用景点/天气/酒店 Agent 收集调研证据。"""
        return self.research_team.run(request, emit, memory_context=memory_context)

    def generate_phase(
        self,
        request: TripRequest,
        research: ResearchBundle,
        knowledge_context: str,
        emit: Callable[[str, str, str, float | None], None],
        memory_context: str = "",
    ) -> TripPlan:
        """阶段2: 整合调研证据与上下文,生成行程并在必要时触发达标择优。"""
        start = time.time()
        emit("行程规划Agent", "running", "正在整合景点、天气、酒店和知识库信息")
        planner_query = build_planner_query(request, research, knowledge_context, memory_context)
        planner_response = self.planner_agent.run(planner_query)
        emit("行程规划Agent", "success", planner_response[:180], start)
        print(f"行程规划结果: {planner_response[:300]}...\n")
        trip_plan = parse_plan_response(planner_response, request)
        trip_plan = improve_plan_if_needed(request, trip_plan, planner_query, emit)
        if research.sources:
            trip_plan.warnings.append("联网搜索结果仅作参考，开放时间与门票请以高德地图数据为准。")
        emit("结果校验", "success", "旅行计划结构化校验完成")
        return trip_plan

    def review_phase(
        self,
        plan: TripPlan,
        request: TripRequest,
        round_index: int,
        emit: Callable[[str, str, str, float | None], None],
        memory_context: str = "",
    ) -> dict[str, Any]:
        """阶段3: 调用审核 Agent 检查行程合理性,返回结构化审核结果。"""
        start = time.time()
        emit("行程审核Agent", "running", f"正在进行第{round_index + 1}轮行程审核")
        review_payload: dict[str, Any] = {"request": request.model_dump(), "plan": plan.model_dump()}
        if memory_context:
            review_payload["memory"] = memory_context
        review_query = json.dumps(review_payload, ensure_ascii=False)
        review_response = self.review_agent.run(review_query)
        review_data = self._parse_review_response(review_response)
        if review_data.get("passed", False):
            emit("行程审核Agent", "success", "审核通过", start)
        else:
            issues = review_data.get("issues", [])
            issue_text = "；".join(str(item) for item in issues) or review_data.get("suggestions", "行程仍需优化")
            emit("行程审核Agent", "failed", issue_text[:180], start)
        return review_data

    def optimize_phase(
        self,
        plan: TripPlan,
        review_data: dict[str, Any],
        request: TripRequest,
        round_index: int,
        emit: Callable[[str, str, str, float | None], None],
        memory_context: str = "",
    ) -> TripPlan:
        """阶段4: 根据审核意见调用修正 Agent 优化行程。"""
        start = time.time()
        emit("行程修正Agent", "running", f"正在根据第{round_index + 1}轮审核意见修正行程")
        current_plan = revise_with_review(self.optimizer_agent, request, plan, review_data, memory_context)
        emit("行程修正Agent", "success", "行程修正完成", start)
        return current_plan

    def enrich_phase(
        self,
        plan: TripPlan,
        request: TripRequest,
        emit: Callable[[str, str, str, float | None], None],
    ) -> TripPlan:
        """阶段5: 补充真实通勤时长、舒适度与备选方案。"""
        return enrich_plan_execution_data(plan, request, emit)

    def _parse_review_response(self, response: str) -> dict[str, Any]:
        try:
            data = parse_json_object(response)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"passed": True, "issues": [], "suggestions": "审核响应解析失败，保留当前行程"}


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
