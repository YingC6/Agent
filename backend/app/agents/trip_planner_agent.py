"""多智能体旅行规划系统"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Any, List
from hello_agents import SimpleAgent
from hello_agents.tools import MCPTool
from ..services.llm_service import get_llm
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
from ..config import get_settings
from ..services.tool_governance import ToolGovernance, ToolPolicy

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
你必须使用工具来搜索景点!不要自己编造景点信息!

**工具调用格式:**
使用maps_text_search工具时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_text_search:keywords=景点关键词,city=城市名]`

**示例:**
用户: "搜索北京的历史文化景点"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=历史文化,city=北京]

用户: "搜索上海的公园"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=公园,city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 参数用逗号分隔
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
你必须使用工具来查询天气!不要自己编造天气信息!

**工具调用格式:**
使用maps_weather工具时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_weather:city=城市名]`

**示例:**
用户: "查询北京天气"
你的回复: [TOOL_CALL:amap_maps_weather:city=北京]

用户: "上海的天气怎么样"
你的回复: [TOOL_CALL:amap_maps_weather:city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
你必须使用工具来搜索酒店!不要自己编造酒店信息!

**工具调用格式:**
使用maps_text_search工具搜索酒店时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_text_search:keywords=酒店,city=城市名]`

**示例:**
用户: "搜索北京的酒店"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=酒店,city=北京]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 关键词使用"酒店"或"宾馆"
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。根据景点和天气信息生成旅行计划。

**直接返回JSON,格式如下:**
```json
{
  "city": "城市名",
  "start_date": "2026-07-01",
  "end_date": "2026-07-02",
  "days": [
    {
      "date": "2026-07-01",
      "day_index": 0,
      "description": "简短描述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名",
        "address": "地址",
        "location": {"longitude": 116.4, "latitude": 39.9},
        "price_range": "200-300元",
        "rating": "4.0",
        "distance": "距离描述",
        "type": "酒店类型",
        "estimated_cost": 250
      },
      "attractions": [
        {
          "name": "景点名",
          "address": "地址",
          "location": {"longitude": 116.397, "latitude": 39.918},
          "visit_duration": 120,
          "description": "简短描述",
          "category": "类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "餐厅名", "description": "描述", "estimated_cost": 30},
        {"type": "lunch", "name": "餐厅名", "description": "描述", "estimated_cost": 50},
        {"type": "dinner", "name": "餐厅名", "description": "描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "2026-07-01",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 30,
      "night_temp": 20,
      "wind_direction": "南风",
      "wind_power": "2级"
    }
  ],
  "overall_suggestions": "简短建议",
  "budget": {
    "total_attractions": 120,
    "total_hotels": 250,
    "total_meals": 160,
    "total_transportation": 50,
    "total": 580
  }
}
```

**要求:** 每天2-3景点,温度纯数字,包含天气和预算。"""

REVIEW_AGENT_PROMPT = """你是行程审核专家。请审核旅行计划是否合理。
只返回JSON,格式如下:
{"passed": true, "issues": [], "suggestions": ""}
如果不合理,passed为false,issues填写问题列表,suggestions填写修改建议。
重点检查:每天景点数量、重复景点、是否符合用户偏好、预算是否异常、天气和行程是否冲突。"""

OPTIMIZER_AGENT_PROMPT = """你是行程修正专家。请根据审核意见修正旅行计划。
只返回完整JSON,格式必须与原旅行计划一致,保留city,start_date,end_date,days,weather_info,overall_suggestions,budget字段。"""


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""

    def __init__(self):
        """初始化多智能体系统"""
        print("🔄 开始初始化多智能体旅行规划系统...")

        try:
            settings = get_settings()
            self.llm = get_llm()

            print("  - 创建MCP工具...")
            env_vars = {"AMAP_MAPS_API_KEY": settings.amap_api_key}
            if settings.amap_security_key:
                env_vars["AMAP_SECURITY_KEY"] = settings.amap_security_key

            def create_amap_tool():
                tool = MCPTool(
                    name="amap",
                    description="高德地图服务",
                    server_command=["uvx", "amap-mcp-server"],
                    env=env_vars,
                    auto_expand=True
                )
                tool.expandable = True
                return tool

            self.attraction_tool = create_amap_tool()
            self.weather_tool = create_amap_tool()
            self.hotel_tool = create_amap_tool()

            # 创建景点搜索Agent
            print("  - 创建景点搜索Agent...")
            self.attraction_agent = SimpleAgent(
                name="景点搜索专家",
                llm=self.llm,
                system_prompt=ATTRACTION_AGENT_PROMPT
            )
            self.attraction_agent.add_tool(self.attraction_tool)

            # 创建天气查询Agent
            print("  - 创建天气查询Agent...")
            self.weather_agent = SimpleAgent(
                name="天气查询专家",
                llm=self.llm,
                system_prompt=WEATHER_AGENT_PROMPT
            )
            self.weather_agent.add_tool(self.weather_tool)

            # 创建酒店推荐Agent
            print("  - 创建酒店推荐Agent...")
            self.hotel_agent = SimpleAgent(
                name="酒店推荐专家",
                llm=self.llm,
                system_prompt=HOTEL_AGENT_PROMPT
            )
            self.hotel_agent.add_tool(self.hotel_tool)

            # 创建行程规划Agent(不需要工具)
            print("  - 创建行程规划Agent...")
            self.planner_agent = SimpleAgent(
                name="行程规划专家",
                llm=self.llm,
                system_prompt=PLANNER_AGENT_PROMPT
            )

            print("  - 创建行程审核Agent...")
            self.review_agent = SimpleAgent(
                name="行程审核专家",
                llm=self.llm,
                system_prompt=REVIEW_AGENT_PROMPT
            )

            print("  - 创建行程修正Agent...")
            self.optimizer_agent = SimpleAgent(
                name="行程修正专家",
                llm=self.llm,
                system_prompt=OPTIMIZER_AGENT_PROMPT
            )

            print(f"✅ 多智能体系统初始化成功")
            print(f"   景点搜索Agent: {len(self.attraction_agent.list_tools())} 个工具")
            print(f"   天气查询Agent: {len(self.weather_agent.list_tools())} 个工具")
            print(f"   酒店推荐Agent: {len(self.hotel_agent.list_tools())} 个工具")

        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def plan_trip(self, request: TripRequest, progress_callback: Callable[[dict], None] | None = None, knowledge_context: str = "") -> TripPlan:
        """
        使用多智能体协作生成旅行计划

        Args:
            request: 旅行请求

        Returns:
            旅行计划
        """
        from ..services.agent_workflow import run_travel_workflow

        steps = []

        def emit(name: str, status: str, summary: str = "", started_at: float | None = None):
            step = {
                "name": name,
                "status": status,
                "summary": summary,
                "duration_ms": int((time.time() - started_at) * 1000) if started_at else 0
            }
            steps.append(step)
            if progress_callback:
                progress_callback(step)

        try:
            print(f"\n{'='*60}")
            print(f"🚀 开始多智能体协作规划旅行(LangGraph 工作流)...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            print(f"{'='*60}\n")

            trip_plan = run_travel_workflow(
                request=request,
                knowledge_context=knowledge_context,
                progress_callback=progress_callback,
                planner=self,
            )

            print(f"{'='*60}")
            print(f"✅ 旅行计划生成完成!")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            emit("异常兜底", "failed", str(e))
            return self._create_fallback_plan(request)

    # ============ LangGraph 工作流阶段方法 ============

    def research_phase(self, request: TripRequest, emit: Callable[[str, str, str, float | None], None]) -> dict[str, str]:
        """阶段1: 并行调用景点/天气/酒店 Agent 收集原始信息。"""
        return self._run_research_agents_parallel(request, emit)

    def generate_phase(
        self,
        request: TripRequest,
        tool_results: dict[str, str],
        knowledge_context: str,
        emit: Callable[[str, str, str, float | None], None],
    ) -> TripPlan:
        """阶段2: 整合工具结果与知识库,调用规划 Agent 生成结构化行程。"""
        start = time.time()
        emit("行程规划Agent", "running", "正在整合景点、天气、酒店和知识库信息")
        planner_query = self._build_planner_query(
            request,
            tool_results.get("attractions", ""),
            tool_results.get("weather", ""),
            tool_results.get("hotels", ""),
            knowledge_context,
        )
        planner_response = self.planner_agent.run(planner_query)
        emit("行程规划Agent", "success", planner_response[:180], start)
        print(f"行程规划结果: {planner_response[:300]}...\n")
        trip_plan = self._parse_response(planner_response, request)
        emit("结果校验", "success", "旅行计划结构化校验完成")
        return trip_plan

    def review_phase(
        self,
        plan: TripPlan,
        request: TripRequest,
        round_index: int,
        emit: Callable[[str, str, str, float | None], None],
    ) -> dict[str, Any]:
        """阶段3: 调用审核 Agent 检查行程合理性,返回结构化审核结果。"""
        start = time.time()
        emit("行程审核Agent", "running", f"正在进行第{round_index + 1}轮行程审核")
        review_query = json.dumps({"request": request.model_dump(), "plan": plan.model_dump()}, ensure_ascii=False)
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
    ) -> TripPlan:
        """阶段4: 根据审核意见调用修正 Agent 优化行程。"""
        start = time.time()
        emit("行程修正Agent", "running", f"正在根据第{round_index + 1}轮审核意见修正行程")
        optimize_query = json.dumps(
            {"request": request.model_dump(), "plan": plan.model_dump(), "review": review_data},
            ensure_ascii=False,
        )
        optimize_response = self.optimizer_agent.run(optimize_query)
        current_plan = self._parse_response(optimize_response, request)
        emit("行程修正Agent", "success", "行程修正完成", start)
        return current_plan

    def enrich_phase(
        self,
        plan: TripPlan,
        request: TripRequest,
        emit: Callable[[str, str, str, float | None], None],
    ) -> TripPlan:
        """阶段5: 补充真实通勤时长、舒适度与备选方案。"""
        return self._enrich_plan_execution_data(plan, request, emit)

    def _run_research_agents_parallel(self, request: TripRequest, emit: Callable[[str, str, str, float | None], None]) -> dict[str, str]:
        tasks = {
            "attractions": ("景点搜索Agent", self.attraction_agent, self._build_attraction_query(request), "正在根据城市和偏好搜索景点"),
            "weather": ("天气查询Agent", self.weather_agent, f"请使用amap_maps_weather工具查询{request.city}天气。\n[TOOL_CALL:amap_maps_weather:city={request.city}]", "正在查询目的地天气"),
            "hotels": ("酒店推荐Agent", self.hotel_agent, f"请使用amap_maps_text_search工具搜索{request.city}的{request.accommodation}酒店。\n[TOOL_CALL:amap_maps_text_search:keywords={request.accommodation}酒店,city={request.city}]", "正在搜索匹配住宿偏好的酒店")
        }
        results: dict[str, str] = {}
        started_at: dict[str, float] = {}
        governance = ToolGovernance([
            ToolPolicy("amap_maps_text_search", ("keywords", "city"), call_limit=2),
            ToolPolicy("amap_maps_weather", ("city",), call_limit=1)
        ])
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for key, (name, agent, query, summary) in tasks.items():
                started_at[key] = time.time()
                emit(name, "running", summary)
                tool_name = "amap_maps_weather" if key == "weather" else "amap_maps_text_search"
                futures[executor.submit(governance.run_agent, tool_name, agent, query)] = key
            for future in as_completed(futures):
                key = futures[future]
                name = tasks[key][0]
                try:
                    result = future.result()
                    results[key] = result
                    emit(name, "success", result[:180], started_at[key])
                    print(f"{name}结果: {result[:200]}...\n")
                except Exception as exc:
                    results[key] = f"{name}执行失败: {exc}"
                    emit(name, "failed", str(exc), started_at[key])
        return results

    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询 - 直接包含工具调用"""
        keywords = []
        if request.preferences:
            keywords = " ".join(request.preferences[:3])
        else:
            keywords = "景点"

        # 直接返回工具调用格式
        query = f"请使用amap_maps_text_search工具搜索{request.city}的{keywords}相关景点。\n[TOOL_CALL:amap_maps_text_search:keywords={keywords},city={request.city}]"
        return query

    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "", knowledge_context: str = "") -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**知识库参考:**
{knowledge_context or '暂无匹配知识'}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query
    
    def _extract_json_data(self, response: str) -> Any:
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "```" in response:
            json_start = response.find("```") + 3
            json_end = response.find("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "{" in response and "}" in response:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            json_str = response[json_start:json_end]
        else:
            raise ValueError("响应中未找到JSON数据")
        return json.loads(json_str)

    def _review_and_optimize_plan(self, plan: TripPlan, request: TripRequest, emit: Callable[[str, str, str, float | None], None]) -> TripPlan:
        """兼容保留:旧版串行审核-修正循环,新流程请使用 review_phase/optimize_phase。"""
        settings = get_settings()
        current_plan = plan
        for round_index in range(settings.max_review_rounds + 1):
            review_data = self.review_phase(current_plan, request, round_index, emit)
            if review_data.get("passed", False):
                return current_plan
            if round_index >= settings.max_review_rounds:
                current_plan.overall_suggestions = f"{current_plan.overall_suggestions}\n系统已完成{settings.max_review_rounds + 1}轮审核，建议出行前再次确认景点开放时间、路线和预算。"
                return current_plan
            current_plan = self.optimize_phase(current_plan, review_data, request, round_index, emit)
        return current_plan

    def _enrich_plan_execution_data(self, plan: TripPlan, request: TripRequest, emit: Callable[[str, str, str, float | None], None]) -> TripPlan:
        """补充每日真实通勤时长、舒适度评估与备选方案。

        调用高德路线规划 API 计算相邻景点之间的真实距离与时长,
        生成 route_segments 供前端绘制交通时间轴;
        单点 API 失败时由 route_service 内部兜底估值,不影响整体流程。
        """
        from ..services.route_service import calculate_day_routes, summarize_transit_minutes

        start = time.time()
        emit("行程可执行性", "running", "正在调用高德路线规划计算每日真实通勤时长")
        total_segments = 0
        for day in plan.days:
            if not day.attractions:
                day.estimated_transit_minutes = 0
                day.route_segments = []
                day.plan_b = "如遇天气变化，建议通过 AI 对话重新安排当天景点。"
                day.comfort_level = "适中"
                continue
            try:
                segments = calculate_day_routes(
                    attractions=day.attractions,
                    city=plan.city,
                    transportation=day.transportation or request.transportation,
                )
                day.route_segments = segments
                day.estimated_transit_minutes = summarize_transit_minutes(segments)
                total_segments += len(segments)
            except Exception as exc:
                print(f"⚠️  第{day.day_index + 1}天路线计算失败,使用估值兜底: {exc}")
                day.estimated_transit_minutes = max(len(day.attractions) - 1, 0) * 20
                day.route_segments = []

            total_visit_minutes = sum(max(attraction.visit_duration or 0, 0) for attraction in day.attractions)
            total_minutes = total_visit_minutes + day.estimated_transit_minutes
            day.comfort_level = "轻松" if total_minutes <= 360 else "适中" if total_minutes <= 540 else "紧凑"

            rain_sensitive_names = "、".join(attraction.name for attraction in day.attractions[:2])
            day.plan_b = (
                f"如遇降雨或拥挤，可优先保留室内场馆，并通过 AI 对话将 {rain_sensitive_names} 替换为附近室内景点。"
                if day.attractions
                else "如遇天气变化，建议通过 AI 对话重新安排当天景点。"
            )
        emit(
            "行程可执行性",
            "success",
            f"已补充{len(plan.days)}天的真实通勤数据,共生成{total_segments}条路段",
            start,
        )
        return plan

    def _parse_review_response(self, response: str) -> dict[str, Any]:
        try:
            data = self._extract_json_data(response)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"passed": True, "issues": [], "suggestions": "审核响应解析失败，保留当前行程"}

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应
        
        Args:
            response: Agent响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        try:
            data = self._extract_json_data(response)
            trip_plan = TripPlan(**data)
            
            return trip_plan
            
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            print(f"   将使用备用方案生成计划")
            return self._create_fallback_plan(request)
    
    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)"""
        from datetime import datetime, timedelta
        
        # 解析日期
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        
        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
                ]
            )
            days.append(day_plan)
        
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。"
        )


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner

