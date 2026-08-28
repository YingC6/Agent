"""对话路由/工具/候选行程确认流程冒烟测试(不依赖LLM与高德)。"""

import json
import os
import sys
import tempfile

_tmp_db = os.path.join(tempfile.gettempdir(), "smoke_test_conversations.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from fastapi.testclient import TestClient

import app.api.routes.conversations as conversations
from app.api.main import app
from app.database import Base, SessionLocal, engine, get_db
from app.models.db_models import TripRecord, User
from app.models.schemas import Attraction, DayPlan, Location, TripPlan
from app.services.security import get_password_hash as hash_password

# ---- Mock 外部依赖 ----

attraction = Attraction(
    name="故宫",
    address="北京市东城区景山前街4号",
    location=Location(longitude=116.397, latitude=39.918),
    visit_duration=180,
    description="明清两代皇宫",
    category="历史文化",
    ticket_price=60,
)
plan = TripPlan(
    city="北京",
    start_date="2026-08-20",
    end_date="2026-08-20",
    overall_suggestions="第一天游览故宫",
    days=[DayPlan(date="2026-08-20", day_index=0, description="历史一日游", transportation="公共交通", accommodation="经济型酒店", attractions=[attraction])],
    weather_info=[],
    budget=None,
)

modified_plan = plan.model_copy(deep=True)
new_attraction = attraction.model_copy(deep=True)
new_attraction.name = "国家博物馆"
modified_plan.days[0].attractions = [new_attraction]

conversations.optimize_trip_plan = lambda plan, instruction: modified_plan

class _FakeAgent:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, prompt):
        return "这是基于当前行程的回答。"

    def stream_run(self, prompt):
        yield "这是基于"
        yield "当前行程的回答。"

conversations.SimpleAgent = _FakeAgent
conversations.get_amap_service = lambda: type("FakeAmap", (), {
    "_call": lambda self, name, args: {"forecast": [{"day_weather": "晴"}]},
    "search_poi_data": lambda self, k, c, citylimit=True: [{"poi_id": "B000A1", "name": "某餐厅"}],
    "plan_route": lambda self, origin, destination, *args: {"route": {"transits": [{"distance": "1200", "duration": "900"}]}},
    "parse_route_summary": lambda self, payload, route_type: {"distance_meters": 1200, "duration_seconds": 900, "route_type": route_type},
})()
conversations.remember_preferences_from_message = lambda db, user_id, content: None
conversations.maybe_summarize_conversation = lambda db, conversation: None


# ---- 准备数据库 ----

Base.metadata.create_all(bind=engine)
db = SessionLocal()
user = User(username="smoke", nickname="smoke", password_hash=hash_password("pass1234"))
db.add(user)
db.commit()
record = TripRecord(user_id=user.id, title="北京1日游", city="北京", start_date="2026-08-20", end_date="2026-08-20", travel_days=1, source="ai", plan_json=plan.model_dump_json())
db.add(record)
db.commit()
trip_id = record.id
db.close()

app.dependency_overrides[get_db] = lambda: (yield SessionLocal())
client = TestClient(app)


def auth_headers():
    login = client.post("/api/auth/login", json={"username": "smoke", "password": "pass1234"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}


def main():
    headers = auth_headers()

    # 1. 创建会话(幂等)
    r1 = client.post("/api/conversations", json={"trip_id": trip_id}, headers=headers)
    assert r1.status_code == 200, r1.text
    conversation_id = r1.json()["data"]["id"]
    r1b = client.post("/api/conversations", json={"trip_id": trip_id}, headers=headers)
    assert r1b.json()["data"]["id"] == conversation_id, "重复创建会话应返回同一会话"
    print("PASS 创建会话幂等")

    # 2. 普通问答(answer 路由, 不调工具)
    r2 = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "第二天去哪玩比较好"}, headers=headers)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()["data"]
    assert body2["message"]["task_status"] == "completed"
    assert body2["pending_change"] is None
    assert body2["message"]["content"] == "这是基于当前行程的回答。"
    steps2 = body2["message"]["task_steps"]
    assert not any("工具" in step["name"] for step in steps2), "普通问答不应调用工具"
    print("PASS answer 路由不调工具")

    # 3. 流式餐厅查询 → meta/delta/done 且调用餐厅工具
    with client.stream("POST", f"/api/conversations/{conversation_id}/messages/stream", json={"content": "故宫附近有什么餐厅"}, headers=headers) as stream_response:
        assert stream_response.status_code == 200, stream_response.text
        stream_text = "\n".join(stream_response.iter_lines())
    assert "event: meta" in stream_text and "restaurant_search" in stream_text
    assert "餐厅推荐" in stream_text
    assert "event: delta" in stream_text and "这是基于当前行程的回答。" in stream_text
    assert "event: done" in stream_text
    print("PASS 流式餐厅查询返回meta/delta/done")

    # 4. 流式交通查询 → 路线工具摘要
    with client.stream("POST", f"/api/conversations/{conversation_id}/messages/stream", json={"content": "从故宫到天坛怎么去"}, headers=headers) as stream_response:
        assert stream_response.status_code == 200, stream_response.text
        transport_text = "\n".join(stream_response.iter_lines())
    assert "transport_search" in transport_text and "故宫 → 天坛" in transport_text
    print("PASS 流式交通查询返回路线摘要")

    # 5. 修改行程 → 候选方案 + 预览, 不落库
    r3 = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "第二天景点换成国家博物馆"}, headers=headers)
    assert r3.status_code == 200, r3.text
    body3 = r3.json()["data"]
    assert body3["pending_change"] is not None, "修改请求应返回候选方案"
    assert "国家博物馆" in body3["pending_change"]["plan"]["days"][0]["attractions"][0]["name"]
    assert body3["message"]["version_id"] is None, "候选方案未确认前不应关联版本"
    check_db = SessionLocal()
    from app.models.db_models import TripVersion
    version_count = len(check_db.query(TripVersion).filter(TripVersion.trip_id == trip_id).all())
    check_db.close()
    assert version_count == 1, f"确认前只应有初始版本, 实际{version_count}"
    print("PASS modify 路由生成候选方案且未落库")

    # 4. 无待确认时发"确认" → 友好回复(先消费掉候选)
    r4 = client.post(f"/api/conversations/{conversation_id}/confirm", json={"action": "cancel"}, headers=headers)
    assert r4.status_code == 200, r4.text
    r4b = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "确认"}, headers=headers)
    assert r4b.status_code == 200, r4b.text
    assert "没有待确认" in r4b.json()["data"]["message"]["content"]
    print("PASS 无候选时确认请求有友好回复")

    # 5. 再生成候选 → 文本"确认"保存 → 新版本落库
    r5 = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "第二天景点换成国家博物馆"}, headers=headers)
    assert r5.status_code == 200 and r5.json()["data"]["pending_change"], r5.text
    r5b = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "确认"}, headers=headers)
    assert r5b.status_code == 200, r5b.text
    body5 = r5b.json()["data"]
    assert body5["message"]["version_id"] is not None, "确认后应产生新版本"
    check_db = SessionLocal()
    versions = check_db.query(TripVersion).filter(TripVersion.trip_id == trip_id).order_by(TripVersion.version_number).all()
    check_db.close()
    assert len(versions) == 2, f"确认后应有2个版本, 实际{len(versions)}"
    assert "国家博物馆" in versions[1].plan_json
    assert versions[1].source == "conversation"
    print("PASS 文本确认保存新版本")

    # 6. 确认接口直接调用(无候选时 404)
    r6 = client.post(f"/api/conversations/{conversation_id}/confirm", json={"action": "confirm"}, headers=headers)
    assert r6.status_code == 404
    print("PASS 无候选时确认接口返回404")

    print("\n全部冒烟测试通过")

if __name__ == "__main__":
    sys.exit(main())
