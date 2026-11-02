"""结构重构特征测试(不依赖LLM与外部服务)。

固化重构前后的关键行为:
1. 规划提示词的逐字输出
2. JSON 解析的成功/失败走向
3. 兜底行程的结构与标记
4. 步骤事件的字段与转发
5. 确定性校验规则与告警合并
"""

import os
import sys
import tempfile

_tmp_db = os.path.join(tempfile.gettempdir(), "smoke_test_structure.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from app.agents.parsers import extract_json, parse_json_object
from app.agents.prompts import build_planner_query
from app.domain.contracts import Evidence, ResearchBundle
from app.domain.fallback import build_fallback_plan
from app.domain.validators.contract import plan_contract_errors
from app.domain.validators.execution import merge_validation_warnings, validate_plan_execution
from app.models.schemas import Attraction, DayPlan, Location, TripPlan, TripRequest
from app.services.plan_validator import validate_plan_execution as exported_validate
from app.workflow.emit import StepEmitter

results: list[tuple[str, bool]] = []


def check(name: str, condition: bool) -> None:
    results.append((name, bool(condition)))


request = TripRequest(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-22",
    travel_days=3,
    transportation="公共交通",
    accommodation="经济型酒店",
    preferences=["历史文化", "美食"],
    free_text_input="想多吃小吃",
)

# 1. 规划提示词必须与重构前逐字一致
research = ResearchBundle(
    attractions=Evidence(raw="故宫、天坛"),
    weather=Evidence(raw="晴,28度"),
    hotels=Evidence(raw="北京饭店"),
)
expected_query = """请根据以下信息生成北京的3天旅行计划:

**基本信息:**
- 城市: 北京
- 日期: 2026-08-20 至 2026-08-22
- 天数: 3天
- 交通方式: 公共交通
- 住宿: 经济型酒店
- 偏好: 历史文化, 美食

**景点信息:**
故宫、天坛

**天气信息:**
晴,28度

**酒店信息:**
北京饭店

**知识库参考:**
参考攻略:胡同

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确

**额外要求:** 想多吃小吃"""
check("规划提示词逐字一致", build_planner_query(request, research, "参考攻略:胡同") == expected_query)

empty_research_query = build_planner_query(
    request.model_copy(update={"free_text_input": ""}),
    ResearchBundle(),
    "",
)
check("空调研结果保留占位符", "暂无匹配知识" in empty_research_query and "故宫" not in empty_research_query)
check("无额外要求时不追加段落", "**额外要求:**" not in empty_research_query)

# 2. 解析成功/失败走向
check("解析代码块JSON", parse_json_object('```json\n{"passed": true}\n```') == {"passed": True})
check("解析裸文本JSON", extract_json('说明文字 {"city": "北京"} 结束') == {"city": "北京"})
try:
    parse_json_object("完全没有JSON的回答")
    check("无JSON时抛错", False)
except ValueError as error:
    check("无JSON时抛错", "未找到JSON数据" in str(error))

# 3. 兜底行程结构
fallback = build_fallback_plan(request, "解析失败")
check("兜底标记正确", fallback.source == "fallback" and fallback.is_fallback is True)
check("兜底天数与请求一致", len(fallback.days) == request.travel_days)
check("兜底警告含原因", any("解析失败" in warning for warning in fallback.warnings))
check("兜底每天2个景点", all(len(day.attractions) == 2 for day in fallback.days))

# 4. 步骤事件字段与转发
emitted: list[dict] = []
emitter = StepEmitter(emitted.append, run_id="a" * 32)
emitter("行程规划Agent", "success", "已完成")
check("步骤事件含run_id与时间戳", emitted and emitted[0]["run_id"] == "a" * 32 and "timestamp_ms" in emitted[0])
check("步骤事件转发给回调", emitted[0]["name"] == "行程规划Agent" and emitter.steps[0]["duration_ms"] == 0)

no_run_id_steps: list[dict] = []
StepEmitter(no_run_id_steps.append)("异常兜底", "failed", "boom")
check("无run_id时保持旧字段", "run_id" not in no_run_id_steps[0])

# 5. 确定性校验与告警合并
attraction = Attraction(
    name="故宫",
    address="北京市东城区",
    location=Location(longitude=116.397, latitude=39.918),
    visit_duration=180,
    description="明清皇宫",
    category="历史文化",
)
day = DayPlan(
    date="2026-08-20",
    day_index=0,
    description="历史一日游",
    transportation="公共交通",
    accommodation="经济型酒店",
    attractions=[attraction],
    estimated_transit_minutes=320,
)
warning_plan = TripPlan(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-20",
    overall_suggestions="测试",
    days=[day],
)
single_day_request = request.model_copy(update={"travel_days": 1, "end_date": "2026-08-20"})
validation = validate_plan_execution(warning_plan, single_day_request)
merged = merge_validation_warnings(warning_plan, validation)
check("校验无阻断错误", validation.passed and validation.errors == [])
check("通勤告警写入行程", any("通勤" in warning for warning in merged.warnings))
check("校验入口保持同名同签名", exported_validate is validate_plan_execution)

try:
    TripPlan(
        city="北京",
        start_date="2026-08-20",
        end_date="2026-08-22",
        overall_suggestions="无日程",
        days=[],
    )
    check("模型契约拦截空行程", False)
except ValueError as error:
    check("模型契约拦截空行程", "行程至少包含一天" in str(error))

empty_plan = TripPlan(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-20",
    overall_suggestions="测试",
    days=[day],
)
check("契约规则可单独调用", plan_contract_errors(empty_plan) == [])

failed = [name for name, ok in results if not ok]
for name, ok in results:
    print(("PASS " if ok else "FAIL ") + name)
print()
if failed:
    raise SystemExit(f"失败 {len(failed)} 项: {failed}")
print("全部结构特征测试通过")
