"""智能体能力配置。

角色 = 名称 + 提示词;工具由各业务装配方按需注入,保证并行 Agent 各持独立工具实例。
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import prompts


@dataclass(frozen=True)
class Capability:
    name: str
    prompt: str


ATTRACTION = Capability(name="景点搜索专家", prompt=prompts.ATTRACTION_AGENT_PROMPT)
WEATHER = Capability(name="天气查询专家", prompt=prompts.WEATHER_AGENT_PROMPT)
HOTEL = Capability(name="酒店推荐专家", prompt=prompts.HOTEL_AGENT_PROMPT)
PLANNER = Capability(name="行程规划专家", prompt=prompts.PLANNER_AGENT_PROMPT)
REVIEW = Capability(name="行程审核专家", prompt=prompts.REVIEW_AGENT_PROMPT)
OPTIMIZER = Capability(name="行程修正专家", prompt=prompts.OPTIMIZER_AGENT_PROMPT)
