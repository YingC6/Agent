"""第二阶段功能特征测试(确定性部分,不依赖LLM与外部服务)。

覆盖:时间表排程、主动澄清、记忆衰减、三源融合结构、联网触发策略、规则评分。
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

_tmp_db = os.path.join(tempfile.gettempdir(), "smoke_test_phase2.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from app.agents.prompts import build_planner_query
from app.domain.clarification import LONG_TRIP_QUESTION, PLAY_STYLE_QUESTION, detect_clarification
from app.domain.contracts import Evidence, ResearchBundle
from app.domain.fallback import build_fallback_plan
from app.domain.scheduler import build_day_timeline
from app.domain.scoring import score_plan
from app.domain.search_policy import should_search_web
from app.domain.sources import format_sources, make_source, rank_sources, time_decay_weight
from app.models.schemas import Attraction, DayPlan, Location, Meal, RouteSegment, TimelineItem, TripPlan, TripRequest
from app.services.memory_service import memory_decay_weight

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))


def make_attraction(name: str, description: str = "") -> Attraction:
    return Attraction(
        name=name,
        address="测试地址",
        location=Location(longitude=116.4, latitude=39.9),
        visit_duration=90,
        description=description,
        category="景点",
    )


def make_request(**overrides) -> TripRequest:
    data = dict(
        city="北京",
        start_date="2026-08-20",
        end_date="2026-08-20",
        travel_days=1,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=["历史文化"],
        free_text_input="",
    )
    data.update(overrides)
    return TripRequest(**data)


day = DayPlan(
    date="2026-08-20",
    day_index=0,
    description="测试行程",
    transportation="公共交通",
    accommodation="经济型酒店",
    attractions=[make_attraction("故宫", "历史文化"), make_attraction("天坛", "历史文化")],
    meals=[
        Meal(type="breakfast", name="早餐店", description="豆浆油条"),
        Meal(type="lunch", name="午餐店", description="面食"),
        Meal(type="dinner", name="晚餐店", description="烤鸭"),
    ],
    route_segments=[RouteSegment(origin="故宫", destination="天坛", duration_minutes=30)],
    estimated_transit_minutes=30,
)
plan = TripPlan(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-20",
    days=[day],
    overall_suggestions="测试",
)

# 1. 时间表排程
timeline = build_day_timeline(day)
check("时间表包含三餐", {item.category for item in timeline} == {"meal", "attraction", "transit"})
check("时间表从早餐开始", timeline[0].time == "08:00" and timeline[0].title == "早餐店")
check("时间表顺序递增", [item.time for item in timeline] == sorted(item.time for item in timeline))
check("时间表包含通勤", any(item.category == "transit" and item.duration_minutes == 30 for item in timeline))
check("晚餐不早于18点", timeline[-1].category == "meal" and timeline[-1].time >= "18:00")
check("时间表条目为结构化对象", all(isinstance(item, TimelineItem) for item in timeline))

# 2. 主动澄清
check("信息不足时提问玩法", detect_clarification(make_request(preferences=[], free_text_input="")) == [PLAY_STYLE_QUESTION])
check("信息充分时不提问", detect_clarification(make_request()) == [])
check("超长行程追加提问", detect_clarification(make_request(travel_days=12)) == [LONG_TRIP_QUESTION])

# 3. 记忆冲突衰减
now = datetime.now()
check("新记忆权重为1", round(memory_decay_weight(now, now), 3) == 1.0)
check("30天后权重减半", round(memory_decay_weight(now - timedelta(days=30), now), 3) == 0.5)
check("更久记忆权重更低", memory_decay_weight(now - timedelta(days=60), now) < memory_decay_weight(now - timedelta(days=10), now))

# 4. 三源融合结构
old_source = make_source("联网搜索", "旧消息", "去年的活动", published_at=(now - timedelta(days=90)).strftime("%Y-%m-%d"))
new_source = make_source("联网搜索", "新消息", "本周开放时间调整", published_at=now.strftime("%Y-%m-%d"))
ranked = rank_sources([old_source, new_source])
check("来源按时效排序", ranked[0]["title"] == "新消息")
check("来源带权重字段", all("weight" in item for item in ranked))
check("来源文本可读", "新消息" in format_sources(ranked) and "本周开放时间调整" in format_sources(ranked))

# 5. 联网搜索三态开关
check("off模式不联网", should_search_web(make_request(search_mode="off", free_text_input="最新的门票")) is False)
check("on模式总是联网", should_search_web(make_request(search_mode="on")) is True)
check("auto模式识别时效意图", should_search_web(make_request(search_mode="auto", free_text_input="想确认最新开放时间")) is True)
check("auto模式普通需求不联网", should_search_web(make_request(search_mode="auto", free_text_input="想吃小吃")) is False)

# 6. 规则评分
check("完整行程缺少预算扣10分", score_plan(plan, make_request()) == 90)
check("兜底行程0分", score_plan(build_fallback_plan(make_request(), "失败"), make_request()) == 0)
thin_plan = TripPlan(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-20",
    days=[day.model_copy(update={"attractions": [make_attraction("故宫", "历史文化")], "meals": [day.meals[0]]})],
    overall_suggestions="测试",
)
check("景点与餐数不足扣分", score_plan(thin_plan, make_request()) == 75)

# 7. 上下文注入
memory_context = "用户长期偏好：偏好：美食"
research = ResearchBundle(attractions=Evidence(raw="故宫"), sources=[new_source])
query_with_extra = build_planner_query(make_request(), research, "攻略", memory_context)
check("记忆注入提示词", "**用户长期记忆:**" in query_with_extra and memory_context in query_with_extra)
check("联网来源注入提示词", "**联网参考信息" in query_with_extra and "新消息" in query_with_extra)
plain_query = build_planner_query(make_request(), ResearchBundle(), "")
check("无额外上下文时不注入", "用户长期记忆" not in plain_query and "联网参考信息" not in plain_query)

# 8. 调研失败识别
failed_bundle = ResearchBundle(weather=Evidence.from_failure("天气查询Agent", "timeout"))
check("失败证据可识别", failed_bundle.failed_keys() == ["weather"])

failed = [name for name, ok in results if not ok]
for name, ok in results:
    print(("PASS " if ok else "FAIL ") + name)
print()
if failed:
    raise SystemExit(f"失败 {len(failed)} 项: {failed}")
print("全部第二阶段特征测试通过")
