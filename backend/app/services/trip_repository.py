"""行程仓储服务"""

import json
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..models.db_models import Conversation, ConversationMessage, GenerationLog, TripRecord, TripVersion
from ..models.schemas import TripPlan, TripRequest


def create_trip_version(db: Session, record: TripRecord, plan: TripPlan, source: str = "ai") -> TripVersion:
    version_number = (db.scalar(select(func.max(TripVersion.version_number)).where(TripVersion.trip_id == record.id)) or 0) + 1
    version = TripVersion(trip_id=record.id, version_number=version_number, plan_json=plan.model_dump_json(), source=source)
    db.add(version)
    record.plan_json = plan.model_dump_json()
    record.source = source
    db.commit()
    db.refresh(version)
    return version


def create_trip_record(db: Session, plan: TripPlan, request: TripRequest | None = None, user_id: int | None = None, source: str = "ai") -> TripRecord:
    record = TripRecord(
        user_id=user_id,
        title=f"{plan.city}{len(plan.days)}日旅行计划",
        city=plan.city,
        start_date=plan.start_date,
        end_date=plan.end_date,
        travel_days=len(plan.days) or (request.travel_days if request else 1),
        source=source,
        plan_json=plan.model_dump_json()
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    create_trip_version(db, record, plan, source)
    return record


def create_trip_version_for_record(db: Session, record: TripRecord, plan: TripPlan, source: str = "conversation") -> TripVersion:
    return create_trip_version(db, record, plan, source)


def list_trip_records(db: Session, user_id: int, keyword: str | None = None, page: int = 1, page_size: int = 10) -> tuple[list[TripRecord], int]:
    stmt = select(TripRecord).where(TripRecord.user_id == user_id)
    if keyword:
        stmt = stmt.where(TripRecord.city.contains(keyword))
    total = len(db.scalars(stmt).all())
    items = db.scalars(stmt.order_by(TripRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(items), total


def version_to_dict(version: TripVersion) -> dict[str, Any]:
    return {"id": version.id, "version_number": version.version_number, "source": version.source, "plan": json.loads(version.plan_json), "created_at": version.created_at.isoformat()}


def trip_to_dict(record: TripRecord) -> dict[str, Any]:
    rating = record.ratings[0] if record.ratings else None
    return {
        "id": record.id,
        "title": record.title,
        "city": record.city,
        "start_date": record.start_date,
        "end_date": record.end_date,
        "travel_days": record.travel_days,
        "source": record.source,
        "plan": json.loads(record.plan_json),
        "versions": [version_to_dict(version) for version in record.versions],
        "rating": {"id": rating.id, "trip_id": rating.trip_id, "rating": rating.rating, "comment": rating.comment} if rating else None,
        "created_at": record.created_at.isoformat()
    }


def conversation_message_to_dict(message: ConversationMessage) -> dict[str, Any]:
    return {"id": message.id, "role": message.role, "content": message.content, "version_id": message.version_id, "task_status": message.task_status, "task_steps": json.loads(message.task_steps_json), "error_message": message.error_message, "duration_ms": message.duration_ms, "created_at": message.created_at.isoformat()}


def conversation_to_dict(conversation: Conversation, include_messages: bool = True) -> dict[str, Any]:
    data = {"id": conversation.id, "trip_id": conversation.trip_id, "current_version_id": conversation.current_version_id, "title": conversation.title, "versions": [version_to_dict(version) for version in conversation.trip.versions] if conversation.trip else [], "created_at": conversation.created_at.isoformat(), "updated_at": conversation.updated_at.isoformat()}
    if include_messages:
        data["messages"] = [conversation_message_to_dict(message) for message in conversation.messages]
    return data


def create_generation_log(db: Session, user_id: int | None, request_text: str, city: str, status: str, steps: list[dict[str, Any]], duration_ms: int = 0, error_message: str = "", trip_id: int | None = None) -> GenerationLog:
    log = GenerationLog(user_id=user_id, trip_id=trip_id, request_text=request_text, city=city, status=status, steps_json=json.dumps(steps, ensure_ascii=False), error_message=error_message, duration_ms=duration_ms)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
