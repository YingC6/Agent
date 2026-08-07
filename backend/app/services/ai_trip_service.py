"""AI行程增强服务"""

import json
import re
from datetime import datetime, timedelta
from hello_agents import SimpleAgent
from ..models.schemas import TripPlan, TripRequest
from .llm_service import get_llm

PARSE_PROMPT = """你是旅行需求解析助手。请把用户自然语言旅行需求解析为JSON。
只返回JSON,字段包括 city,start_date,end_date,travel_days,transportation,accommodation,preferences,free_text_input。
日期未知时从明天开始,默认2天。transportation默认公共交通,accommodation默认经济型酒店,preferences为字符串数组。"""

OPTIMIZE_PROMPT = """你是行程优化助手。请根据用户修改要求优化已有旅行计划。
只返回完整JSON,格式必须与原旅行计划一致,保留city,start_date,end_date,days,weather_info,overall_suggestions,budget字段。"""


def extract_json(text: str) -> dict:
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end]
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end]
    else:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group()
    return json.loads(text.strip())


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
        free_text_input=extra
    )


def parse_natural_language(text: str) -> TripRequest:
    try:
        agent = SimpleAgent(name="旅行需求解析Agent", llm=get_llm(), system_prompt=PARSE_PROMPT)
        response = agent.run(text)
        data = extract_json(response)
        return TripRequest(**data)
    except Exception:
        return fallback_parse(text)


def optimize_trip_plan(plan: TripPlan, instruction: str) -> TripPlan:
    try:
        agent = SimpleAgent(name="行程优化Agent", llm=get_llm(), system_prompt=OPTIMIZE_PROMPT)
        response = agent.run(json.dumps({"plan": plan.model_dump(), "instruction": instruction}, ensure_ascii=False))
        data = extract_json(response)
        return TripPlan(**data)
    except Exception:
        plan.overall_suggestions = f"{plan.overall_suggestions}\n优化建议: {instruction}。建议根据该要求适当调整景点数量、交通和预算。"
        return plan
