"""追踪功能验证:run_id 贯穿、节点级事件、审核循环、确定性校验、结构化日志、SSE 与落库。"""

import os
import sys
import tempfile
import threading
import time

_tmp_db = os.path.join(tempfile.gettempdir(), "verify_tracking.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from fastapi.testclient import TestClient
from loguru import logger

# ============ Part A: LangGraph 工作流级验证 ============

from app.models.schemas import Attraction, DayPlan, Location, TripPlan, TripRequest
from app.services.agent_workflow import run_travel_workflow

request = TripRequest(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-20",
    travel_days=1,
    transportation="公共交通",
    accommodation="经济型酒店",
)


def make_plan(city="北京", attraction_name="故宫", warnings=None):
    attraction = Attraction(
        name=attraction_name,
        address="北京市东城区",
        location=Location(longitude=116.397, latitude=39.918),
        visit_duration=120,
        description="著名景点",
        category="历史文化",
    )
    return TripPlan(
        city=city,
        start_date="2026-08-20",
        end_date="2026-08-20",
        overall_suggestions="测试行程",
        days=[DayPlan(date="2026-08-20", day_index=0, description="一日游", transportation="公共交通", accommodation="经济型酒店", attractions=[attraction])],
        weather_info=[],
        warnings=warnings or [],
    )


class FakePlanner:
    """模拟 MultiAgentTripPlanner 的各阶段行为。"""

    def __init__(self, review_results, plan=None):
        self.review_results = review_results  # 每轮审核的 passed 结果
        self.review_calls = 0
        self.optimize_calls = 0
        self.plan = plan or make_plan()

    def research_phase(self, request, emit):
        emit("景点搜索Agent", "success", "找到3个景点")
        return {"attractions": "故宫 天坛", "weather": "晴", "hotels": "某酒店"}

    def generate_phase(self, request, tool_results, knowledge_context, emit):
        emit("行程规划Agent", "success", "已生成行程")
        return self.plan

    def review_phase(self, plan, request, round_index, emit):
        self.review_calls += 1
        passed = self.review_results[min(self.review_calls - 1, len(self.review_results) - 1)]
        emit("行程审核Agent", "success", f"第{self.review_calls}轮审核{'通过' if passed else '不通过'}")
        return {"passed": passed, "reasons": []}

    def optimize_phase(self, plan, review_data, request, round_index, emit):
        self.optimize_calls += 1
        emit("行程修正Agent", "success", "已修正")
        return self.plan

    def enrich_phase(self, plan, request, emit):
        emit("行程可执行性", "success", "已补充通勤与备选方案")
        return self.plan


# 捕获 loguru 结构化日志
captured_logs: list[str] = []
log_sink = lambda message: captured_logs.append(message.record["message"])
logger.add(log_sink, level="INFO")

print("=" * 60)
print("Part A: LangGraph 工作流追踪验证")
print("=" * 60)

# A1: run_id 贯穿 + 节点顺序 + 审核循环(第1轮不通过→修正→第2轮通过)
steps_a: list[dict] = []
planner = FakePlanner(review_results=[False, True])  # 第1轮不通过, 第2轮通过
run_id_a = "testrunid" + "a" * 24
plan_a = run_travel_workflow(request, "", steps_a.append, planner=planner, run_id=run_id_a)

assert all(s.get("run_id") == run_id_a for s in steps_a), "存在缺少 run_id 的步骤事件"
node_names = [s["name"] for s in steps_a]
print(f"\nA1 步骤序列({len(steps_a)}步): {node_names}")
assert "LangGraph工作流" in node_names
assert "确定性行程校验" in node_names, "validate_execution 节点未执行"
assert planner.review_calls == 2, f"审核应执行2轮, 实际{planner.review_calls}"
assert planner.optimize_calls == 1, f"修正应执行1次, 实际{planner.optimize_calls}"
print(f"A1 PASS run_id贯穿全部{len(steps_a)}步; 审核2轮+修正1次; 校验节点已执行")

# A2: 确定性校验拦截非法行程(城市不一致)
planner_bad = FakePlanner(review_results=[True], plan=make_plan(city="错误城市"))
try:
    run_travel_workflow(request, "", lambda s: None, planner=planner_bad, run_id="bad" * 11)
    raise AssertionError("城市不一致的行程应被 validate_execution 拦截")
except ValueError as error:
    print(f"A2 PASS 确定性校验拦截: {error}")

# A3: 确定性校验告警写入 plan.warnings
plan_warning = make_plan()
plan_warning.days[0].estimated_transit_minutes = 320  # 超过300分钟阈值
planner_warn = FakePlanner(review_results=[True], plan=plan_warning)
plan_result = run_travel_workflow(request, "", lambda s: None, planner=planner_warn, run_id="warn" * 11)
assert any("通勤" in w for w in plan_result.warnings), f"告警应写入 warnings, 实际: {plan_result.warnings}"
print(f"A3 PASS 通勤告警已写入 plan.warnings: {[w for w in plan_result.warnings if '通勤' in w]}")

# A4: 结构化日志 workflow_started / workflow_step / workflow_completed
joined = "\n".join(captured_logs)
assert f"workflow_started run_id={run_id_a}" in joined, "缺少 workflow_started 日志"
assert f"workflow_completed run_id={run_id_a}" in joined, "缺少 workflow_completed 日志"
step_logs = [line for line in captured_logs if line.startswith("workflow_step")]
assert any(f"run_id={run_id_a}" in line for line in step_logs), "workflow_step 日志缺少 run_id"
assert any("workflow_failed run_id=" in line for line in captured_logs), "workflow_failed 日志未记录"
print(f"A4 PASS 结构化日志: workflow_started/completed/step({len(step_logs)}条)/failed 均含 run_id")

logger.remove()  # 停止捕获

# ============ Part B: SSE 接口级验证(真实 HTTP 路径) ============

print()
print("=" * 60)
print("Part B: SSE 接口 run_id 追踪与落库验证")
print("=" * 60)

import app.api.routes.trip as trip_module
from app.api.main import app
from app.database import Base, SessionLocal, engine, get_db
from app.models.db_models import GenerationLog, User
from app.services.security import get_password_hash

class FakeHttpPlanner:
    def plan_trip(self, request, progress_callback=None, knowledge_context="", run_id=""):
        if progress_callback:
            progress_callback({"name": "景点搜索Agent", "status": "success", "summary": "mock完成", "duration_ms": 5})
            progress_callback({"name": "行程规划Agent", "status": "success", "summary": "mock完成", "duration_ms": 5})
        return make_plan()

trip_module.get_trip_planner_agent = lambda: FakeHttpPlanner()
trip_module.get_cached_plan = lambda request, user_id: None
trip_module.check_plan_rate_limit = lambda user_id, client_key: (True, 0)
trip_module.set_cached_plan = lambda request, plan, user_id: None


class FakeRetrieval:
    context = ""

    def refs(self):
        return []


trip_module.run_agentic_retrieval = lambda db, request, progress=None: FakeRetrieval()

Base.metadata.create_all(bind=engine)
db = SessionLocal()
user = User(username="track", nickname="track", password_hash=get_password_hash("pass1234"))
db.add(user)
db.commit()
db.close()
app.dependency_overrides[get_db] = lambda: (yield SessionLocal())
client = TestClient(app)

login = client.post("/api/auth/login", json={"username": "track", "password": "pass1234"})
token = login.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

with client.stream(
    "GET",
    "/api/trip/plan/stream",
    params={"city": "北京", "start_date": "2026-08-20", "end_date": "2026-08-20", "travel_days": 1, "token": token},
    headers=headers,
) as response:
    assert response.status_code == 200, response.text
    sse_lines = [line for line in response.iter_lines()]

events = []
for line in sse_lines:
    if line.startswith("data: "):
        import json as _json
        events.append(_json.loads(line[6:]))

step_events = [e for e in events if "name" in e]
done_events = [e for e in events if "plan" in e]
run_ids = {e.get("run_id") for e in step_events + done_events}
print(f"\nB1 SSE事件: {len(step_events)}个step + {len(done_events)}个done")
print(f"   步骤: {[e['name'] for e in step_events]}")
assert len(run_ids) == 1 and None not in run_ids, f"run_id 不一致: {run_ids}"
sse_run_id = run_ids.pop()
assert len(sse_run_id) == 32, f"run_id 应为32位hex, 实际: {sse_run_id}"
print(f"B1 PASS 全部SSE事件携带同一 run_id={sse_run_id[:12]}...")

check_db = SessionLocal()
logs = check_db.query(GenerationLog).order_by(GenerationLog.id.desc()).all()
latest = logs[0]
steps_in_db = __import__("json").loads(latest.steps_json)
db_run_ids = {s.get("run_id") for s in steps_in_db}
assert db_run_ids == {sse_run_id}, f"落库步骤 run_id({db_run_ids}) 与 SSE run_id({sse_run_id}) 不一致"
assert latest.status == "success"
print(f"B2 PASS 落库日志 id={latest.id}: {len(steps_in_db)}步的 run_id 与 SSE 完全一致, status=success")
check_db.close()

print("\n" + "=" * 60)
print("全部追踪功能验证通过")
print("=" * 60)
