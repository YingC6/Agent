"""旅行规划API路由"""

import json
import queue
import threading
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ...api.deps import get_optional_user
from ...agents.trip_planner_agent import get_trip_planner_agent
from ...database import SessionLocal, get_db
from ...models.schemas import TripPlan, TripPlanResponse, TripRequest
from ...services.ai_guard_service import check_plan_rate_limit, get_cached_plan, set_cached_plan
from ...services.ai_trip_service import optimize_trip_plan, parse_natural_language
from ...services.knowledge_service import build_knowledge_context, search_relevant_knowledge
from ...services.plan_diff_service import compute_plan_diff
from ...services.trip_repository import create_generation_log, create_trip_record, trip_to_dict

router = APIRouter(prefix="/trip", tags=["旅行规划"])


class NaturalLanguageRequest(BaseModel):
    text: str = Field(..., min_length=4)


class OptimizeRequest(BaseModel):
    plan: dict
    instruction: str = Field(..., min_length=2)


@router.post("/parse")
def parse_trip_request(request: NaturalLanguageRequest):
    parsed = parse_natural_language(request.text)
    return {"success": True, "message": "解析成功", "data": parsed.model_dump()}


@router.post("/plan", response_model=TripPlanResponse)
async def plan_trip(request_data: TripRequest, http_request: Request, current_user=Depends(get_optional_user), db: Session = Depends(get_db)):
    started_at = time.time()
    steps = []

    def collect(step: dict):
        steps.append(step)

    try:
        user_id = current_user.id if current_user else None
        cached_plan = get_cached_plan(request_data, user_id)
        if cached_plan:
            collect({"name": "AI结果缓存", "status": "success", "summary": "命中相同旅行需求缓存,直接返回历史生成结果", "duration_ms": 0})
            record = create_trip_record(db, cached_plan, request_data, user_id, source="cache") if user_id else None
            duration_ms = int((time.time() - started_at) * 1000)
            create_generation_log(db, user_id, request_data.free_text_input or "表单生成", request_data.city, "success", steps, duration_ms, trip_id=record.id if record else None)
            return TripPlanResponse(success=True, message="旅行计划生成成功(缓存)", data=cached_plan)

        allowed, retry_after = check_plan_rate_limit(user_id, http_request.client.host if http_request.client else "anonymous")
        if not allowed:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"生成过于频繁,请{retry_after}秒后再试")

        knowledge_items = search_relevant_knowledge(db, request_data)
        knowledge_context = build_knowledge_context(knowledge_items)
        if knowledge_items:
            collect({"name": "知识库检索", "status": "success", "summary": f"匹配到{len(knowledge_items)}条旅行经验", "duration_ms": 0})
        agent = get_trip_planner_agent()
        trip_plan = agent.plan_trip(request_data, progress_callback=collect, knowledge_context=knowledge_context)
        set_cached_plan(request_data, trip_plan, user_id)
        record = None
        if current_user:
            record = create_trip_record(db, trip_plan, request_data, current_user.id)
        duration_ms = int((time.time() - started_at) * 1000)
        create_generation_log(db, user_id, request_data.free_text_input or "表单生成", request_data.city, "success", steps, duration_ms, trip_id=record.id if record else None)
        return TripPlanResponse(success=True, message="旅行计划生成成功", data=trip_plan)
    except HTTPException:
        raise
    except Exception as e:
        create_generation_log(db, current_user.id if current_user else None, request_data.free_text_input or "表单生成", request_data.city, "failed", steps, int((time.time() - started_at) * 1000), str(e))
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")


@router.get("/plan/stream")
def stream_plan(http_request: Request, city: str = Query(...), start_date: str = Query(...), end_date: str = Query(...), travel_days: int = Query(..., ge=1, le=30), transportation: str = Query(default="公共交通"), accommodation: str = Query(default="经济型酒店"), preferences: str = Query(default=""), free_text_input: str = Query(default=""), current_user=Depends(get_optional_user), db: Session = Depends(get_db)):
    request = TripRequest(
        city=city,
        start_date=start_date,
        end_date=end_date,
        travel_days=travel_days,
        transportation=transportation,
        accommodation=accommodation,
        preferences=[item for item in preferences.split(",") if item],
        free_text_input=free_text_input
    )
    user_id = current_user.id if current_user else None
    client_key = http_request.client.host if http_request.client else "anonymous"

    def event_generator():
        started_at = time.time()
        steps = []
        events: queue.Queue = queue.Queue()
        done_marker = object()

        def collect(step: dict):
            steps.append(step)
            events.put({"type": "step", "data": step})

        def worker():
            worker_db = SessionLocal()
            try:
                events.put({"type": "step", "data": {"name": "任务初始化", "status": "running", "summary": "开始生成旅行计划", "duration_ms": 0}})
                cached_plan = get_cached_plan(request, user_id)
                if cached_plan:
                    collect({"name": "AI结果缓存", "status": "success", "summary": "命中相同旅行需求缓存,直接返回历史生成结果", "duration_ms": 0})
                    record = create_trip_record(worker_db, cached_plan, request, user_id, source="cache") if user_id else None
                    duration_ms = int((time.time() - started_at) * 1000)
                    log = create_generation_log(worker_db, user_id, free_text_input or "流式生成", city, "success", steps, duration_ms, trip_id=record.id if record else None)
                    events.put({"type": "done", "data": {"plan": cached_plan.model_dump(), "trip_id": record.id if record else None, "log_id": log.id}})
                    return
                allowed, retry_after = check_plan_rate_limit(user_id, client_key)
                if not allowed:
                    events.put({"type": "error", "data": {"message": f"生成过于频繁,请{retry_after}秒后再试"}})
                    return
                knowledge_items = search_relevant_knowledge(worker_db, request)
                knowledge_context = build_knowledge_context(knowledge_items)
                if knowledge_items:
                    collect({"name": "知识库检索", "status": "success", "summary": f"匹配到{len(knowledge_items)}条旅行经验", "duration_ms": 0})
                agent = get_trip_planner_agent()
                trip_plan = agent.plan_trip(request, progress_callback=collect, knowledge_context=knowledge_context)
                set_cached_plan(request, trip_plan, user_id)
                record = None
                if user_id:
                    record = create_trip_record(worker_db, trip_plan, request, user_id)
                duration_ms = int((time.time() - started_at) * 1000)
                log = create_generation_log(worker_db, user_id, free_text_input or "流式生成", city, "success", steps, duration_ms, trip_id=record.id if record else None)
                events.put({"type": "done", "data": {"plan": trip_plan.model_dump(), "trip_id": record.id if record else None, "log_id": log.id}})
            except Exception as e:
                create_generation_log(worker_db, user_id, free_text_input or "流式生成", city, "failed", steps, int((time.time() - started_at) * 1000), str(e))
                events.put({"type": "error", "data": {"message": str(e)}})
            finally:
                worker_db.close()
                events.put(done_marker)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            event = events.get()
            if event is done_marker:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/optimize")
def optimize_trip(request: OptimizeRequest, current_user=Depends(get_optional_user), db: Session = Depends(get_db)):
    try:
        original_plan = TripPlan(**request.plan)
        optimized = optimize_trip_plan(original_plan, request.instruction)
        # 计算优化前后的差异摘要,供前端预览变更
        diff = compute_plan_diff(original_plan, optimized)
        record = None
        if current_user:
            record = create_trip_record(db, optimized, user_id=current_user.id, source="optimized")
        return {"success": True, "message": "优化成功", "data": {"plan": optimized.model_dump(), "diff": diff, "trip": trip_to_dict(record) if record else None}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"优化失败: {str(e)}")


@router.get("/health")
async def health_check():
    try:
        agent = get_trip_planner_agent()
        return {"status": "healthy", "service": "trip-planner", "agent_name": agent.planner_agent.name}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")
