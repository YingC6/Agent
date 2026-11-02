"""AI行程增强服务

负责自然语言需求解析与用户指令驱动的行程优化,
具体解析/提示词/重试语义均复用 agents 与 revision_service 的共享实现。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..agents.parsers import extract_json
from ..agents.prompts import PARSE_PROMPT
from ..agents.registry import get_agent
from ..models.schemas import TripPlan, TripRequest
from .revision_service import optimize_with_instruction


def fallback_parse(text: str) -> TripRequest:
    city_match = re.search(r"去([\u4e00-\u9fa5]{2,10})", text) or re.search(r"([\u4e00-\u9fa5]{2,10})玩", text)
    days_match = re.search(r"(\d+)\s*天", text)
    budget_match = re.search(r"预算\s*(\d+)", text)
    city = city_match.group(1) if city_match else "北京"
    days = int(days_match.group(1)) if days_match else 2
    start = datetime.now() + timedelta(days=1)
    end = start + timedelta(days=days - 1)
    preferences = []
    for item in ["美食", "历史文化", "自然风光", "购物", "艺术", "休闲"]:
        if item in text:
            preferences.append(item)
    extra = text
    if budget_match:
        extra += f"\n预算约{budget_match.group(1)}元"
    return TripRequest(
        city=city,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        travel_days=days,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=preferences or ["休闲"],
        free_text_input=extra,
    )


def parse_natural_language(text: str) -> TripRequest:
    try:
        response = get_agent("trip_parse", "旅行需求解析Agent", PARSE_PROMPT).run(text)
        return TripRequest(**extract_json(response))
    except Exception:
        return fallback_parse(text)


def optimize_trip_plan(plan: TripPlan, instruction: str) -> TripPlan:
    return optimize_with_instruction(plan, instruction)
