import json
import re
import time
from collections.abc import Generator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from hello_agents import SimpleAgent
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import Conversation, ConversationMessage, TripRecord, TripVersion
from ...models.schemas import TripPlan, TripRequest
from ...services.ai_trip_service import optimize_trip_plan
from ...services.amap_service import get_amap_service
from ...services.context_builder import build_conversation_context
from ...services.knowledge_agent import run_agentic_retrieval
from ...services.llm_service import get_llm
from ...services.memory_service import remember_preferences_from_message
from ...services.plan_diff_service import compute_plan_diff
from ...services.plan_validator import validate_plan_execution
from ...services.summary_service import maybe_summarize_conversation
from ...services.trip_repository import conversation_to_dict, create_trip_version_for_record, trip_to_dict

router = APIRouter(prefix="/conversations", tags=["行程对话"])
_PENDING_CHANGES: dict[int, dict[str, Any]] = {}


class ConversationCreateRequest(BaseModel):
    trip_id: int = Field(..., gt=0)
    title: str = Field(default="旅行计划对话", max_length=160)


class ConversationMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class ConversationConfirmRequest(BaseModel):
    action: Literal["confirm", "cancel"]


class ConversationIntent(BaseModel):
    name: Literal["confirm", "cancel", "modify", "weather", "restaurant_search", "transport_search", "poi_search", "answer"]
    query: str = ""
    origin: str = ""
    destination: str = ""
    route_type: Literal["walking", "driving", "transit"] = "transit"


def get_owned_conversation(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conversation


def _request_from_plan(plan: TripPlan) -> TripRequest:
    transportation = plan.days[0].transportation if plan.days else "公共交通"
    accommodation = plan.days[0].accommodation if plan.days else "经济型酒店"
    return TripRequest(city=plan.city, start_date=plan.start_date, end_date=plan.end_date, travel_days=len(plan.days), transportation=transportation, accommodation=accommodation)


def _route_message(content: str) -> ConversationIntent:
    normalized = content.strip().lower()
    if normalized in {"确认", "确认修改", "就这样", "应用", "保存"}:
        return ConversationIntent(name="confirm")
    if normalized in {"取消", "取消修改", "放弃", "不要了"}:
        return ConversationIntent(name="cancel")
    if any(word in content for word in ("换", "替换", "增加", "删除", "调整", "改成", "改为", "预算", "重新安排")):
        return ConversationIntent(name="modify", query=content)
    if any(word in content for word in ("天气", "下雨", "温度", "晴", "降雨")):
        return ConversationIntent(name="weather", query=content)
    if any(word in content for word in ("餐厅", "餐馆", "美食", "吃饭", "早餐", "午餐", "晚餐")):
        return ConversationIntent(name="restaurant_search", query=content)
    if any(word in content for word in ("怎么去", "路线", "路程", "公交", "地铁", "驾车", "步行", "交通")):
        route_type = "driving" if any(word in content for word in ("驾车", "开车", "自驾")) else "walking" if "步行" in content else "transit"
        parts = re.split(r"(?:到|至|去|→)", content, maxsplit=1)
        origin = re.sub(r".*?(?:从|由)", "", parts[0]).strip() if len(parts) > 1 else ""
        destination = parts[1].strip("？?。！! ") if len(parts) > 1 else ""
        return ConversationIntent(name="transport_search", query=content, origin=origin, destination=destination, route_type=route_type)
    if any(word in content for word in ("附近", "酒店", "景点", "地点", "哪里")):
        return ConversationIntent(name="poi_search", query=content)
    return ConversationIntent(name="answer", query=content)


def _tool_context(intent: ConversationIntent, content: str, plan: TripPlan) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if intent.name not in {"weather", "restaurant_search", "transport_search", "poi_search", "modify"}:
        return "", [], []
    service = get_amap_service()
    steps: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    try:
        if intent.name == "weather":
            result = service._call("maps_weather", {"city": plan.city})
            steps.append({"name": "天气查询工具", "status": "success", "summary": f"已查询{plan.city}天气", "duration_ms": 0})
            results.append({"type": "weather", "title": f"{plan.city}天气", "data": result})
        elif intent.name == "transport_search":
            origin = intent.origin or (plan.days[0].hotel.address if plan.days and plan.days[0].hotel else plan.city)
            destination = intent.destination or plan.days[0].attractions[0].address
            result = service.plan_route(origin, destination, plan.city, plan.city, intent.route_type)
            summary = service.parse_route_summary(result, intent.route_type)
            steps.append({"name": "交通路线查询工具", "status": "success", "summary": f"已查询{origin}到{destination}的路线", "duration_ms": 0})
            results.append({"type": "transport", "title": f"{origin} → {destination}", "data": summary})
        else:
            keywords = f"{plan.city} 餐厅 {content[:60]}" if intent.name == "restaurant_search" else content[:80] if intent.name == "poi_search" else f"{plan.city} {content[:60]}"
            pois = service.search_poi_data(keywords, plan.city)[:5]
            title = "餐厅推荐" if intent.name == "restaurant_search" else "地点搜索结果"
            steps.append({"name": "餐厅查询工具" if intent.name == "restaurant_search" else "地点搜索工具", "status": "success", "summary": f"已找到{len(pois)}个{title}候选", "duration_ms": 0})
            results.append({"type": "restaurant" if intent.name == "restaurant_search" else "poi", "title": title, "data": pois})
        return f"实时查询结果：{json.dumps(results, ensure_ascii=False)[:1800]}", steps, results
    except Exception as error:
        steps.append({"name": "实时查询工具", "status": "failed", "summary": "工具暂不可用，已基于当前行程继续处理", "duration_ms": 0})
        logger.warning("conversation_tool_failed intent={} error={}", intent.name, str(error))
        return "实时工具查询失败，请避免把未验证信息当作事实。", steps, []


# 纯寒暄类消息不触发知识检索,避免给简短问候增加一次检索开销
CHITCHAT_ONLY = {"你好", "hi", "hello", "嗨", "在吗", "谢谢", "再见", "好的"}


def _should_retrieve_knowledge(content: str) -> bool:
    text = content.strip().lower()
    return len(text) >= 4 and text not in CHITCHAT_ONLY


def _knowledge_context(content: str, plan: TripPlan, db: Session) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """对话场景的知识检索:限制单轮并跳过LLM重排,避免拖慢聊天响应。"""
    if not _should_retrieve_knowledge(content):
        return "", [], []
    request = _request_from_plan(plan).model_copy(update={"free_text_input": content})
    try:
        retrieval = run_agentic_retrieval(db, request, max_rounds=1, rerank=False)
    except Exception as error:
        logger.warning("conversation_knowledge_failed error={}", str(error))
        return "", [], []
    refs = retrieval.refs()
    if not refs:
        return "", [], []
    steps = [{"name": "知识库检索", "status": "success", "summary": f"检索到{len(refs)}条相关攻略", "duration_ms": 0}]
    results = [{"type": "knowledge", "title": "知识库参考", "data": refs}]
    return "知识库参考(仅作参考,事实以实时查询为准):\n" + retrieval.context, steps, results


def _append_message(db: Session, conversation: Conversation, role: str, content: str, version_id: int | None, task_status: str, task_steps: list[dict[str, Any]], started_at: float, error_message: str = "") -> ConversationMessage:
    message = ConversationMessage(conversation_id=conversation.id, role=role, content=content, version_id=version_id, task_status=task_status, task_steps_json=json.dumps(task_steps, ensure_ascii=False), error_message=error_message, duration_ms=int((time.monotonic() - started_at) * 1000))
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _message_to_dict(message: ConversationMessage) -> dict[str, Any]:
    return {"id": message.id, "role": message.role, "content": message.content, "version_id": message.version_id, "task_status": message.task_status, "task_steps": json.loads(message.task_steps_json), "error_message": message.error_message, "duration_ms": message.duration_ms, "created_at": message.created_at.isoformat()}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_text(content: str) -> Generator[str, None, None]:
    for index in range(0, len(content), 24):
        yield _sse("delta", {"content": content[index:index + 24]})


def _stream_agent_response(prompt: str) -> Generator[str, None, None]:
    agent = SimpleAgent(name="行程多轮对话Agent", llm=get_llm(), system_prompt="请使用中文，简洁、准确地协助旅行计划调整。")
    stream = getattr(agent, "stream_run", None)
    if not callable(stream):
        response = agent.run(prompt)
        for index in range(0, len(response), 24):
            yield response[index:index + 24]
        return
    for chunk in stream(prompt):
        text = str(chunk)
        if text:
            yield text


@router.post("")
def create_conversation(request: ConversationCreateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    trip = db.get(TripRecord, request.trip_id)
    if not trip or trip.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="行程不存在")
    existing = next((item for item in trip.conversations if item.user_id == current_user.id), None)
    if existing:
        return {"success": True, "message": "对话已存在", "data": conversation_to_dict(existing)}
    version = max(trip.versions, key=lambda item: item.version_number, default=None) if trip.versions else create_trip_version_for_record(db, trip, TripPlan(**json.loads(trip.plan_json)), trip.source)
    conversation = Conversation(user_id=current_user.id, trip_id=trip.id, current_version_id=version.id, title=request.title or trip.title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {"success": True, "message": "对话已创建", "data": conversation_to_dict(conversation)}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return {"success": True, "message": "查询成功", "data": conversation_to_dict(get_owned_conversation(db, conversation_id, current_user.id))}


@router.post("/{conversation_id}/confirm")
def confirm_pending_change(conversation_id: int, request: ConversationConfirmRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = get_owned_conversation(db, conversation_id, current_user.id)
    pending = _PENDING_CHANGES.get(conversation.id)
    if not pending:
        raise HTTPException(status_code=404, detail="没有待确认的行程修改")
    if request.action == "cancel":
        _PENDING_CHANGES.pop(conversation.id, None)
        return {"success": True, "message": "已放弃候选修改", "data": {"conversation": conversation_to_dict(conversation), "pending_change": None}}
    trip = db.get(TripRecord, conversation.trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    version = create_trip_version_for_record(db, trip, pending["plan"], "conversation")
    conversation.current_version_id = version.id
    db.commit()
    _PENDING_CHANGES.pop(conversation.id, None)
    return {"success": True, "message": "已保存行程修改", "data": {"conversation": conversation_to_dict(conversation), "trip": trip_to_dict(trip), "version_id": version.id, "pending_change": None}}


def _load_message_context(conversation_id: int, request: ConversationMessageRequest, current_user: Any, db: Session) -> tuple[Conversation, TripRecord, TripVersion | None, TripPlan, ConversationIntent, float]:
    started_at = time.monotonic()
    conversation = get_owned_conversation(db, conversation_id, current_user.id)
    trip = db.get(TripRecord, conversation.trip_id) if conversation.trip_id else None
    if not trip:
        raise HTTPException(status_code=400, detail="对话尚未关联行程")
    version = db.get(TripVersion, conversation.current_version_id) if conversation.current_version_id else None
    plan = TripPlan(**json.loads(version.plan_json if version else trip.plan_json))
    _append_message(db, conversation, "user", request.content, version.id if version else None, "completed", [], started_at)
    return conversation, trip, version, plan, _route_message(request.content), started_at


def _process_message(conversation_id: int, request: ConversationMessageRequest, current_user: Any, db: Session) -> tuple[dict[str, Any], ConversationIntent]:
    conversation, trip, version, plan, intent, started_at = _load_message_context(conversation_id, request, current_user, db)
    try:
        if intent.name in {"confirm", "cancel"}:
            if conversation.id not in _PENDING_CHANGES:
                assistant_message = _append_message(db, conversation, "assistant", "当前没有待确认的行程修改。请先描述你想调整的内容，例如“第二天换成室内景点”。", version.id if version else None, "completed", [], started_at)
                result = {"conversation": conversation_to_dict(conversation), "message": _message_to_dict(assistant_message), "trip": trip_to_dict(trip), "pending_change": None, "intent": intent.model_dump(), "query_results": []}
            else:
                confirmed = confirm_pending_change(conversation_id, ConversationConfirmRequest(action=intent.name), current_user, db)
                reply = "已保存候选行程修改。" if intent.name == "confirm" else "已放弃候选行程修改。"
                assistant_message = _append_message(db, conversation, "assistant", reply, confirmed["data"].get("version_id"), "completed", [{"name": "候选行程处理", "status": "success", "summary": reply, "duration_ms": int((time.monotonic() - started_at) * 1000)}], started_at)
                result = {"conversation": conversation_to_dict(conversation), "message": _message_to_dict(assistant_message), "trip": confirmed["data"].get("trip") or trip_to_dict(trip), "pending_change": confirmed["data"].get("pending_change"), "intent": intent.model_dump(), "query_results": []}
            return result, intent
        remember_preferences_from_message(db, current_user.id, request.content)
        tool_context, task_steps, query_results = _tool_context(intent, request.content, plan)
        knowledge_context = ""
        if intent.name == "answer":
            knowledge_context, knowledge_steps, knowledge_results = _knowledge_context(request.content, plan, db)
            task_steps.extend(knowledge_steps)
            query_results.extend(knowledge_results)
        if intent.name == "modify":
            candidate = optimize_trip_plan(plan, f"{request.content}\n{tool_context}")
            validation = validate_plan_execution(candidate, _request_from_plan(plan))
            if validation.errors:
                raise ValueError("；".join(validation.errors))
            if validation.warnings:
                candidate.warnings = [*candidate.warnings, *validation.warnings]
            diff = compute_plan_diff(plan, candidate)
            _PENDING_CHANGES[conversation.id] = {"plan": candidate, "diff": diff}
            response = f"已生成候选修改：{diff['summary']}。请查看预览后回复“确认”保存，或回复“取消”放弃。"
            task_steps.append({"name": "候选行程生成", "status": "success", "summary": diff["summary"], "duration_ms": 0})
            pending_change, version_id = {"plan": candidate.model_dump(), "diff": diff}, None
        else:
            prompt = "你是旅行行程助手。基于当前计划、用户长期偏好和最近对话回答用户。实时查询结果仅作参考，不能编造事实。请使用中文，简洁回答。\n" + build_conversation_context(conversation, plan, db=db) + "\n" + tool_context + "\n" + knowledge_context + "\n用户最新请求: " + request.content
            response = SimpleAgent(name="行程多轮对话Agent", llm=get_llm(), system_prompt="请使用中文，简洁、准确地协助旅行计划调整。").run(prompt)
            task_steps.append({"name": "对话回答", "status": "success", "summary": "已生成回复", "duration_ms": 0})
            pending_change, version_id = None, version.id if version else None
        assistant_message = _append_message(db, conversation, "assistant", response, version_id, "completed", task_steps, started_at)
        maybe_summarize_conversation(db, conversation)
        db.refresh(conversation)
        return {"conversation": conversation_to_dict(conversation), "message": _message_to_dict(assistant_message), "trip": trip_to_dict(trip), "pending_change": pending_change, "intent": intent.model_dump(), "query_results": query_results}, intent
    except Exception as error:
        assistant_message = _append_message(db, conversation, "assistant", "抱歉，处理本次请求失败，请稍后重试。", version.id if version else None, "failed", [{"name": "对话任务", "status": "failed", "summary": "处理失败", "duration_ms": int((time.monotonic() - started_at) * 1000)}], started_at, str(error))
        logger.exception("conversation_message conversation_id={} status=failed", conversation.id)
        return {"conversation": conversation_to_dict(conversation), "message": _message_to_dict(assistant_message), "trip": trip_to_dict(trip), "pending_change": None, "intent": intent.model_dump(), "query_results": []}, intent


@router.post("/{conversation_id}/messages")
def send_message(conversation_id: int, request: ConversationMessageRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    result, _ = _process_message(conversation_id, request, current_user, db)
    return {"success": True, "message": "回复成功" if result["message"]["task_status"] == "completed" else "处理失败", "data": result}


@router.post("/{conversation_id}/messages/stream")
def stream_message(conversation_id: int, request: ConversationMessageRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    intent = _route_message(request.content)

    def generate() -> Generator[str, None, None]:
        yield _sse("meta", {"intent": intent.model_dump(), "query_results": []})
        if intent.name in {"confirm", "cancel", "modify"}:
            result, _ = _process_message(conversation_id, request, current_user, db)
            yield _sse("meta", {"intent": intent.model_dump(), "query_results": result["query_results"]})
            yield from _stream_text(result["message"]["content"])
            yield _sse("done", result)
            return
        started_at = time.monotonic()
        conversation = None
        version = None
        try:
            conversation, trip, version, plan, _, _ = _load_message_context(conversation_id, request, current_user, db)
            remember_preferences_from_message(db, current_user.id, request.content)
            tool_context, task_steps, query_results = _tool_context(intent, request.content, plan)
            knowledge_context = ""
            if intent.name == "answer":
                knowledge_context, knowledge_steps, knowledge_results = _knowledge_context(request.content, plan, db)
                task_steps.extend(knowledge_steps)
                query_results.extend(knowledge_results)
            yield _sse("meta", {"intent": intent.model_dump(), "query_results": query_results})
            prompt = "你是旅行行程助手。基于当前计划、用户长期偏好和最近对话回答用户。实时查询结果仅作参考，不能编造事实。请使用中文，简洁回答。\n" + build_conversation_context(conversation, plan, db=db) + "\n" + tool_context + "\n" + knowledge_context + "\n用户最新请求: " + request.content
            chunks: list[str] = []
            for chunk in _stream_agent_response(prompt):
                chunks.append(chunk)
                yield _sse("delta", {"content": chunk})
            response = "".join(chunks)
            task_steps.append({"name": "对话回答", "status": "success", "summary": "已生成流式回复", "duration_ms": 0})
            assistant_message = _append_message(db, conversation, "assistant", response, version.id if version else None, "completed", task_steps, started_at)
            maybe_summarize_conversation(db, conversation)
            db.refresh(conversation)
            result = {"conversation": conversation_to_dict(conversation), "message": _message_to_dict(assistant_message), "trip": trip_to_dict(trip), "pending_change": None, "intent": intent.model_dump(), "query_results": query_results}
            yield _sse("done", result)
        except Exception as error:
            logger.exception("conversation_stream conversation_id={} status=failed", conversation_id)
            if conversation is not None:
                assistant_message = _append_message(db, conversation, "assistant", "抱歉，处理本次请求失败，请稍后重试。", version.id if version else None, "failed", [{"name": "对话任务", "status": "failed", "summary": "处理失败", "duration_ms": int((time.monotonic() - started_at) * 1000)}], started_at, str(error))
                result = {"conversation": conversation_to_dict(conversation), "message": _message_to_dict(assistant_message), "trip": None, "pending_change": None, "intent": intent.model_dump(), "query_results": []}
                yield _sse("done", result)
            else:
                yield _sse("error", {"message": "对话处理失败"})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
