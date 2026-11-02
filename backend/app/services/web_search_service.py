"""联网搜索服务(可插拔)。

未配置 TAVILY_API_KEY 时自动降级为不可用,不会发起任何请求。
返回的来源统一经 domain.sources.make_source 归一化。
"""

from __future__ import annotations

import os

import httpx
from loguru import logger

from ..domain.sources import make_source
from ..models.schemas import TripRequest

TAVILY_ENDPOINT = "https://api.tavily.com/search"


def is_available() -> bool:
    return bool(os.getenv("TAVILY_API_KEY"))


def build_web_query(request: TripRequest, memory_context: str = "") -> str:
    """把请求压缩成一条时效性检索查询。"""
    preferences = " ".join(request.preferences or [])
    query = f"{request.city} {preferences} 最新 开放时间 门票 活动"
    if memory_context:
        memory_text = memory_context.split("：", 1)[-1].replace("；", " ")[:40]
        query = f"{query} {memory_text}"
    return query


def search_web(request: TripRequest, limit: int = 3, memory_context: str = "") -> list[dict]:
    """联网检索;任何异常都返回空列表,不影响主流程。"""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return []
    try:
        response = httpx.post(
            TAVILY_ENDPOINT,
            json={"api_key": api_key, "query": build_web_query(request, memory_context), "max_results": limit, "search_depth": "basic"},
            timeout=15,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            make_source(
                source="联网搜索",
                title=item.get("title", ""),
                content=(item.get("content") or "")[:200],
                url=item.get("url", ""),
                published_at=item.get("published_date", ""),
            )
            for item in results[:limit]
        ]
    except Exception as error:
        logger.warning("web_search_failed error={}", str(error))
        return []
