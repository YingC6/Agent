"""并行调研小组:景点 / 天气 / 酒店。

每个 Agent 持有独立的 MCPTool 实例,并通过统一并行执行器调度。
"""

from __future__ import annotations

from typing import Any, Callable

from hello_agents.tools import MCPTool

from ...domain.contracts import Evidence, ResearchBundle
from ...domain.search_policy import should_search_web
from ...domain.sources import rank_sources
from ...services.tool_governance import ToolGovernance, ToolPolicy
from ...services.web_search_service import is_available, search_web
from ...workflow.fanout import ParallelTask, run_parallel
from ..prompts import build_attraction_query, build_hotel_query, build_weather_query
from ..runtime import AgentRuntime
from .trip import ATTRACTION, HOTEL, WEATHER


def create_amap_tool(env_vars: dict[str, str]) -> MCPTool:
    tool = MCPTool(
        name="amap",
        description="高德地图服务",
        # uvx 默认会解析到最新 pydantic,与 amap-mcp-server 依赖的 mcp 1.x 不兼容,
        # 会报 eval_type_backport 导入失败,这里显式锁定 pydantic 版本
        server_command=["uvx", "--with", "pydantic<2.11", "amap-mcp-server"],
        env=env_vars,
        auto_expand=True,
    )
    tool.expandable = True
    return tool


class ResearchTeam:
    """负责一次请求内的三类并行调研,出口为 ResearchBundle。"""

    def __init__(self, env_vars: dict[str, str]):
        self.attraction_agent = AgentRuntime(
            name=ATTRACTION.name, system_prompt=ATTRACTION.prompt, tools=[create_amap_tool(env_vars)]
        )
        self.weather_agent = AgentRuntime(
            name=WEATHER.name, system_prompt=WEATHER.prompt, tools=[create_amap_tool(env_vars)]
        )
        self.hotel_agent = AgentRuntime(
            name=HOTEL.name, system_prompt=HOTEL.prompt, tools=[create_amap_tool(env_vars)]
        )

    def run(self, request: Any, emit: Callable[[str, str, str, float | None], None], memory_context: str = "") -> ResearchBundle:
        governance = ToolGovernance([
            ToolPolicy("amap_maps_text_search", ("keywords", "city"), call_limit=2),
            ToolPolicy("amap_maps_weather", ("city",), call_limit=1),
        ])
        tasks = [
            ParallelTask(
                key="attractions",
                name="景点搜索Agent",
                summary="正在根据城市和偏好搜索景点",
                run=lambda: governance.run_agent("amap_maps_text_search", self.attraction_agent, build_attraction_query(request, memory_context)),
            ),
            ParallelTask(
                key="weather",
                name="天气查询Agent",
                summary="正在查询目的地天气",
                run=lambda: governance.run_agent("amap_maps_weather", self.weather_agent, build_weather_query(request)),
            ),
            ParallelTask(
                key="hotels",
                name="酒店推荐Agent",
                summary="正在搜索匹配住宿偏好的酒店",
                run=lambda: governance.run_agent("amap_maps_text_search", self.hotel_agent, build_hotel_query(request, memory_context)),
            ),
        ]
        names = {task.key: task.name for task in tasks}
        if should_search_web(request) and is_available():
            tasks.append(ParallelTask(
                key="web",
                name="联网搜索",
                summary="正在检索最新时效性信息",
                run=lambda: rank_sources(search_web(request, memory_context=memory_context)),
            ))
            names["web"] = "联网搜索"
        elif should_search_web(request):
            emit("联网搜索", "success", "未配置 TAVILY_API_KEY，已跳过联网检索")
        else:
            emit("联网搜索", "success", "auto 模式未识别到时效性需求，已跳过联网检索")

        evidence: dict[str, Evidence] = {}
        sources: list[dict] = []
        for outcome in run_parallel(tasks, emit):
            if outcome.key == "web" and not outcome.error:
                sources = outcome.value
            elif outcome.error:
                evidence[outcome.key] = Evidence.from_failure(names[outcome.key], outcome.error)
            else:
                evidence[outcome.key] = Evidence(raw=str(outcome.value))

        return ResearchBundle(
            attractions=evidence.get("attractions", Evidence()),
            weather=evidence.get("weather", Evidence()),
            hotels=evidence.get("hotels", Evidence()),
            sources=sources,
        )
