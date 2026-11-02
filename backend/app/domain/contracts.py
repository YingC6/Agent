"""跨层数据契约。

节点之间只允许传递这里的类型化对象,禁止把 LLM 原始文本直接塞进下一个 Agent 的提示词。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evidence:
    """一次外部调研的证据。

    本轮先承载 Agent 原始文本,后续可在同一契约内替换为结构化 POI 列表,
    调用方无需感知。
    """
    raw: str = ""
    ok: bool = True
    error: str = ""

    @classmethod
    def from_failure(cls, name: str, error: str) -> "Evidence":
        return cls(raw=f"{name}执行失败: {error}", ok=False, error=error)


@dataclass
class ResearchBundle:
    """research 节点的出口:景点/天气/酒店三类调研证据。"""
    attractions: Evidence = field(default_factory=Evidence)
    weather: Evidence = field(default_factory=Evidence)
    hotels: Evidence = field(default_factory=Evidence)
    sources: list[dict[str, Any]] = field(default_factory=list)

    def attractions_text(self) -> str:
        return self.attractions.raw

    def weather_text(self) -> str:
        return self.weather.raw

    def hotels_text(self) -> str:
        return self.hotels.raw

    def failed_keys(self) -> list[str]:
        return [
            key
            for key, evidence in (("attractions", self.attractions), ("weather", self.weather), ("hotels", self.hotels))
            if not evidence.ok
        ]
