"""AI行程增强服务"""

import json
import re
from datetime import datetime, timedelta
from hello_agents import SimpleAgent
from ..models.schemas import TripPlan, TripRequest
from .llm_service import get_llm
import logging

logger = logging.getLogger(__name__)

PARSE_PROMPT = """你是旅行需求解析助手。请把用户自然语言旅行需求解析为JSON。
只返回JSON,字段包括 city,start_date,end_date,travel_days,transportation,accommodation,preferences,free_text_input。
日期未知时从明天开始,默认2天。transportation默认公共交通,accommodation默认经济型酒店,preferences为字符串数组。"""

OPTIMIZE_PROMPT = """你是行程优化助手。请根据用户修改要求优化已有旅行计划。

**你必须真正修改行程内容,不能原样返回!**

优化原则:
1. 仔细阅读用户的修改要求(instruction字段)
2. 根据要求调整景点(增删替换)、餐饮、交通、住宿、预算
3. 保持JSON结构不变,但内容必须有实质变化
4. 如果用户要求减少预算,则降低酒店档次或减少收费景点
5. 如果用户要求增加某类景点,则替换或新增对应景点
6. 如果用户要求调整天数,则增减days数组

**输出格式(重要):**
直接返回行程对象本身的JSON,顶层字段为 city,start_date,end_date,days,weather_info,overall_suggestions,budget。
不要把结果包裹在 "plan" 键中!不要返回 ```json 代码块,直接返回纯JSON。"""


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


def _extract_plan_data(data: dict) -> dict:
    """从 LLM 返回的 JSON 中提取行程数据。

    LLM 可能返回两种结构:
    1. 直接的行程对象: {"city": "...", "days": [...]}
    2. 嵌套结构: {"plan": {"city": "...", "days": [...]}}(模仿输入格式)
    """
    if isinstance(data, dict) and "plan" in data and isinstance(data["plan"], dict):
        return data["plan"]
    return data


def optimize_trip_plan(plan: TripPlan, instruction: str) -> TripPlan:
    import time as _time

    plan_json = json.dumps({"plan": plan.model_dump(), "instruction": instruction}, ensure_ascii=False)
    last_error = "未知错误"

    for attempt in range(2):
        try:
            agent = SimpleAgent(name="行程优化Agent", llm=get_llm(), system_prompt=OPTIMIZE_PROMPT)
            response = agent.run(plan_json)
            logger.info("optimize_response attempt=%d length=%d preview=%s", attempt, len(response), response[:200])
            data = _extract_plan_data(extract_json(response))
            new_plan = TripPlan(**data)

            # 检测是否有实质变化
            old_names = {a.name for day in plan.days for a in day.attractions}
            new_names = {a.name for day in new_plan.days for a in day.attractions}
            if old_names == new_names and new_plan.budget.total == plan.budget.total:
                logger.warning("optimize_no_change detected, instruction=%s", instruction[:100])
                if attempt == 0:
                    plan_json = json.dumps({
                        "plan": plan.model_dump(),
                        "instruction": f"请务必修改行程! {instruction}",
                        "reminder": "上次返回的行程与原行程完全相同,请根据要求做实质性调整"
                    }, ensure_ascii=False)
                    continue

            logger.info("optimize_success attempt=%d attractions_old=%d attractions_new=%d",
                        attempt, len(old_names), len(new_names))
            return new_plan
        except Exception as error:
            last_error = str(error)
            logger.error("optimize_failed attempt=%d error=%s", attempt, last_error, exc_info=True)
            if attempt == 0:
                _time.sleep(1)
                continue

    # 两次都失败,返回原计划并标注
    logger.warning("optimize_fallback returning original plan with suggestion text")
    plan.overall_suggestions = f"{plan.overall_suggestions}\n⚠️ AI优化未能成功生成新方案(原因: {last_error[:100]})。手动建议: {instruction}"
    return plan
