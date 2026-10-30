"""知识检索分块透传与 Agentic RAG 循环冒烟测试(不依赖LLM与嵌入服务)。"""

import os
import tempfile

_tmp_db = os.path.join(tempfile.gettempdir(), "smoke_test_rag.db")
if os.path.exists(_tmp_db):
    os.remove(_tmp_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

from app.api.routes.conversations import _knowledge_context, _should_retrieve_knowledge
from app.database import Base, SessionLocal, engine
from app.models.schemas import Attraction, DayPlan, Location, TripPlan, TripRequest
from app.services import knowledge_agent, knowledge_service
from app.services.knowledge_service import (
    build_knowledge_context,
    create_knowledge_item,
    retrieve_knowledge,
    search_relevant_knowledge,
    split_knowledge_chunks,
)

Base.metadata.create_all(bind=engine)
db = SessionLocal()

CONTENT = "第一天清晨去了胡同。中午在老街吃了炸酱面。下午逛公园。晚上回酒店休息。" * 30
item = create_knowledge_item(db, {
    "title": "北京胡同亲子三日游",
    "city": "北京",
    "days": 3,
    "themes": "亲子、历史文化",
    "keywords": "胡同、老街、公园",
    "content": CONTENT,
})

chunks = split_knowledge_chunks(item)
assert len(chunks) >= 2, "测试资料长度不足以产生多个分块"
second_chunk = chunks[1]

# 避免真实 LLM 调用
knowledge_service.rerank_knowledge_with_llm = lambda request, candidates, limit: candidates[:limit]

beijing = TripRequest(
    city="北京", start_date="2026-11-01", end_date="2026-11-03", travel_days=3,
    transportation="公共交通", accommodation="经济型酒店", preferences=["亲子"],
)
shanghai = TripRequest(
    city="上海", start_date="2026-11-01", end_date="2026-11-03", travel_days=3,
    transportation="公共交通", accommodation="经济型酒店", preferences=["购物"],
)

results = []


def check(name, condition):
    results.append((name, bool(condition)))


# 1. 向量命中的分块必须原样进入上下文,不被重新切分覆盖
knowledge_service._vector_recall = lambda items, query, top_k=8: [(0.78, second_chunk)]
hits = retrieve_knowledge(db, beijing, limit=3)
context = build_knowledge_context(hits)
check("向量命中分块透传", len(hits) == 1 and hits[0].chunk.index == 1)
check("上下文使用命中分块", second_chunk.content in context)
check("上下文不再注入未命中的首块", chunks[0].content not in context)
check("上下文带溯源信息", "匹配分" in context and "来源" in context)

# 2. 规则召回也要挑出分块,向量不可用时正常降级
knowledge_service._vector_recall = lambda items, query, top_k=8: []
hits = retrieve_knowledge(db, beijing, limit=3)
check("向量不可用时降级为规则召回", len(hits) == 1 and hits[0].source == "rule")
check("规则召回带分块", hits[0].chunk is not None)

# 3. 兼容入口仍返回条目本体
items = search_relevant_knowledge(db, beijing)
check("兼容入口返回知识条目", len(items) == 1 and items[0].title == "北京胡同亲子三日游")

# 4. 召回充分时只跑一轮,不触发查询改写
progress = []
rewrite_calls = []
knowledge_agent._rewrite_query = lambda request, base, reason: rewrite_calls.append(reason) or "北京 亲子 胡同"
knowledge_service._vector_recall = lambda items, query, top_k=8: [(0.78, second_chunk)]
result = knowledge_agent.run_agentic_retrieval(db, beijing, progress=progress.append)
check("召回充分只跑一轮", result.rounds == 1 and len(result.traces) == 1)
check("充分性标记正确", result.traces[0].sufficient is True)
check("充分时未改写查询", rewrite_calls == [])
check("轨迹记录写入进度", any("知识库检索" in step["name"] for step in progress))

# 5. 召回不足时改写查询并重检,最多两轮
round_queries = []


def fake_retrieve(session, request, limit=3, query=None, rerank=True):
    round_queries.append(query)
    if query is None:
        return []
    return [hits[0]]


knowledge_agent.retrieve_knowledge = fake_retrieve
progress = []
result = knowledge_agent.run_agentic_retrieval(db, shanghai, progress=progress.append)
check("召回不足触发两轮检索", result.rounds == 2 and len(result.traces) == 2)
check("第一轮无结果判为不充分", result.traces[0].sufficient is False)
check("改写查询生效", round_queries[0] is None and round_queries[1] == "北京 亲子 胡同")
check("改写步骤写入进度", any("检索查询改写" in step["name"] for step in progress))
check("第二轮召回进入结果", len(result.hits) == 1)

# 6. 溯源信息结构完整
refs = result.refs()
check(
    "溯源字段完整",
    refs and {"id", "title", "city", "score", "source"} <= set(refs[0].keys()),
)

# 7. 对话场景:rerank=False 时跳过 LLM 重排,且寒暄不触发检索
knowledge_agent.retrieve_knowledge = knowledge_service.retrieve_knowledge
rerank_calls_fast = []
knowledge_service.rerank_knowledge_with_llm = lambda request, candidates, limit: rerank_calls_fast.append(1) or candidates[:limit]
fast_hits = retrieve_knowledge(db, beijing, limit=3, rerank=False)
check("对话检索跳过LLM重排", len(fast_hits) == 1 and rerank_calls_fast == [])
pd_attraction = Attraction(
    name="故宫", address="北京市东城区", location=Location(longitude=116.397, latitude=39.918),
    visit_duration=180, description="明清皇宫", category="历史文化", ticket_price=60,
)
pd_plan = TripPlan(
    city="北京", start_date="2026-11-01", end_date="2026-11-01", overall_suggestions="历史一日游",
    days=[DayPlan(date="2026-11-01", day_index=0, description="历史一日游", transportation="公共交通", accommodation="经济型酒店", attractions=[pd_attraction])],
)
ctx, steps, results_kb = _knowledge_context("北京亲子三日游怎么安排", pd_plan, db)
check("对话知识检索注入上下文", bool(ctx) and results_kb and results_kb[0]["type"] == "knowledge")
check("对话知识检索写入步骤", steps and steps[0]["name"] == "知识库检索")
check("寒暄消息不触发知识检索", _should_retrieve_knowledge("你好") is False and _should_retrieve_knowledge("北京亲子三日游怎么安排") is True)

db.close()

failed = [name for name, ok in results if not ok]
for name, ok in results:
    print(("PASS " if ok else "FAIL ") + name)
print()
if failed:
    raise SystemExit(f"失败 {len(failed)} 项: {failed}")
print("全部 RAG 冒烟测试通过")
