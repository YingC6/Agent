import json
import time
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from hello_agents import SimpleAgent
from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import Conversation, ConversationMessage, TripRecord, TripVersion
from ...models.schemas import TripPlan
from ...services.ai_trip_service import extract_json
from ...services.context_builder import build_conversation_context
from ...services.llm_service import get_llm
from ...services.memory_service import remember_preferences_from_message
from ...services.summary_service import maybe_summarize_conversation
from ...services.trip_repository import conversation_to_dict, create_trip_version_for_record, trip_to_dict

router = APIRouter(prefix="/conversations", tags=["行程对话"])
RECENT_MESSAGE_LIMIT = 8


class ConversationCreateRequest(BaseModel):
    trip_id: int = Field(..., gt=0)
    title: str = Field(default="旅行计划对话", max_length=160)


class ConversationMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


def get_owned_conversation(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conversation


def build_context(conversation: Conversation, plan: TripPlan, db: Session) -> str:
    return build_conversation_context(conversation, plan, db=db)


@router.post("")
def create_conversation(request: ConversationCreateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    trip = db.get(TripRecord, request.trip_id)
    if not trip or trip.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="行程不存在")
    version = trip.versions[-1] if trip.versions else create_trip_version_for_record(db, trip, TripPlan(**json.loads(trip.plan_json)), trip.source)
    conversation = Conversation(user_id=current_user.id, trip_id=trip.id, current_version_id=version.id, title=request.title or trip.title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {"success": True, "message": "对话已创建", "data": conversation_to_dict(conversation)}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = get_owned_conversation(db, conversation_id, current_user.id)
    return {"success": True, "message": "查询成功", "data": conversation_to_dict(conversation)}


@router.post("/{conversation_id}/messages")
def send_message(conversation_id: int, request: ConversationMessageRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    started_at = time.monotonic()
    conversation = get_owned_conversation(db, conversation_id, current_user.id)
    trip = db.get(TripRecord, conversation.trip_id) if conversation.trip_id else None
    if not trip:
        raise HTTPException(status_code=400, detail="对话尚未关联行程")
    version = db.get(TripVersion, conversation.current_version_id) if conversation.current_version_id else None
    plan = TripPlan(**json.loads(version.plan_json if version else trip.plan_json))
    user_message = ConversationMessage(conversation_id=conversation.id, role="user", content=request.content, version_id=version.id if version else None, task_status="completed")
    assistant_message = ConversationMessage(conversation_id=conversation.id, role="assistant", content="", version_id=version.id if version else None, task_status="running", task_steps_json=json.dumps([{"name": "对话任务", "status": "running", "summary": "正在结合当前行程和最近对话处理请求", "duration_ms": 0}], ensure_ascii=False))
    db.add_all([user_message, assistant_message])
    db.commit()
    try:
        remember_preferences_from_message(db, current_user.id, request.content)
        prompt = "你是旅行行程助手。基于当前计划、用户长期偏好和最近对话，回答用户。只有用户明确要求修改行程时，才在回答后附加完整的更新后计划，格式为 <TRIP_PLAN_JSON>{完整JSON}</TRIP_PLAN_JSON>。计划必须严格保留既有字段并满足每天1至3个景点、连续day_index、预算总额等于明细之和。\n" + build_context(conversation, plan, db) + "\n用户最新请求: " + request.content
        response = SimpleAgent(name="行程多轮对话Agent", llm=get_llm(), system_prompt="请使用中文，简洁、准确地协助旅行计划调整。").run(prompt)
        updated_plan = None
        if "<TRIP_PLAN_JSON>" in response and "</TRIP_PLAN_JSON>" in response:
            raw_plan = response.split("<TRIP_PLAN_JSON>", 1)[1].split("</TRIP_PLAN_JSON>", 1)[0].strip()
            updated_plan = TripPlan(**extract_json(raw_plan))
            response = response.split("<TRIP_PLAN_JSON>", 1)[0].strip()
        if updated_plan:
            new_version = create_trip_version_for_record(db, trip, updated_plan, "conversation")
            conversation.current_version_id = new_version.id
            assistant_message.version_id = new_version.id
        assistant_message.content = response or "已根据你的要求更新行程。"
        assistant_message.task_status = "completed"
        assistant_message.task_steps_json = json.dumps([{"name": "对话任务", "status": "success", "summary": "已生成回复并保存行程版本" if updated_plan else "已生成回复", "duration_ms": int((time.monotonic() - started_at) * 1000)}], ensure_ascii=False)
        assistant_message.duration_ms = int((time.monotonic() - started_at) * 1000)
        db.commit()
        db.refresh(assistant_message)
        # 对话消息超过阈值时自动生成摘要,避免上下文窗口溢出
        maybe_summarize_conversation(db, conversation)
        db.refresh(conversation)
        logger.info("conversation_message conversation_id={} status=completed version_id={} duration_ms={}", conversation.id, assistant_message.version_id, assistant_message.duration_ms)
        return {"success": True, "message": "回复成功", "data": {"conversation": conversation_to_dict(conversation), "message": {"id": assistant_message.id, "role": assistant_message.role, "content": assistant_message.content, "version_id": assistant_message.version_id, "task_status": assistant_message.task_status, "task_steps": json.loads(assistant_message.task_steps_json), "duration_ms": assistant_message.duration_ms, "created_at": assistant_message.created_at.isoformat()}, "trip": trip_to_dict(trip)}}
    except Exception as error:
        assistant_message.content = "抱歉，处理本次请求失败，请稍后重试。"
        assistant_message.task_status = "failed"
        assistant_message.error_message = str(error)
        assistant_message.duration_ms = int((time.monotonic() - started_at) * 1000)
        assistant_message.task_steps_json = json.dumps([{"name": "对话任务", "status": "failed", "summary": str(error), "duration_ms": assistant_message.duration_ms}], ensure_ascii=False)
        db.commit()
        logger.exception("conversation_message conversation_id={} status=failed", conversation.id)
        raise HTTPException(status_code=500, detail="对话处理失败")
