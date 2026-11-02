"""多源信息统一结构:站内攻略、高德数据、联网搜索都归一成同一份来源记录。

冲突处理原则:高德 API 的数据优先,联网结果只作补充参考。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

HALF_LIFE_DAYS = 30
DEFAULT_WEIGHT = 0.6


def make_source(
    source: str,
    title: str,
    content: str,
    url: str = "",
    published_at: str = "",
) -> dict[str, Any]:
    """构造统一来源记录。"""
    return {
        "source": source,
        "title": title,
        "content": content,
        "url": url,
        "published_at": published_at,
    }


def time_decay_weight(published_at: str, now: datetime | None = None) -> float:
    """按发布时间计算时效权重:每过 30 天权重减半。"""
    if not published_at:
        return DEFAULT_WEIGHT
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return DEFAULT_WEIGHT
    now = now or datetime.now(published.tzinfo)
    days = max((now - published).days, 0)
    return 0.5 ** (days / HALF_LIFE_DAYS)


def rank_sources(sources: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """按权重排序并去重(标题相同视为同一条)。"""
    ranked = sorted(sources, key=lambda item: time_decay_weight(item.get("published_at", "")), reverse=True)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in ranked:
        key = (item.get("title") or item.get("content") or "")[:40]
        if key in seen:
            continue
        seen.add(key)
        result.append({**item, "weight": round(time_decay_weight(item.get("published_at", "")), 3)})
        if len(result) >= limit:
            break
    return result


def format_sources(sources: list[dict[str, Any]]) -> str:
    """把来源记录拼成提示词可读文本。"""
    lines = []
    for item in sources:
        published = f"（{item['published_at']}）" if item.get("published_at") else ""
        lines.append(f"- [{item.get('source', '未知来源')}] {item.get('title', '')}{published}：{item.get('content', '')}")
    return "\n".join(lines)
