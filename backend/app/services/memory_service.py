import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.db_models import UserMemory


def list_user_memories(db: Session, user_id: int, limit: int = 8) -> list[UserMemory]:
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def build_user_memory_context(db: Session, user_id: int) -> str:
    memories = list_user_memories(db, user_id)
    if not memories:
        return ""
    return "用户长期偏好：" + "；".join(memory.content for memory in memories)


def remember_preferences_from_message(db: Session, user_id: int, content: str) -> None:
    patterns = [
        (r"(?:我|用户)?(?:喜欢|偏好|想要)([^。！？；]{2,80})", "preference"),
        (r"(?:我|用户)?(?:不喜欢|不要|不想)([^。！？；]{2,80})", "avoidance"),
        (r"(?:预算|花费).{0,20}(?:控制在|不超过|以内)([^。！？；]{1,40})", "budget"),
    ]
    created = False
    for pattern, memory_type in patterns:
        match = re.search(pattern, content)
        if not match:
            continue
        prefix = "偏好" if memory_type == "preference" else "避开" if memory_type == "avoidance" else "预算"
        memory_content = f"{prefix}：{match.group(1).strip()}"
        exists = db.scalar(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.memory_type == memory_type,
                UserMemory.content == memory_content,
            )
        )
        if not exists:
            db.add(UserMemory(user_id=user_id, memory_type=memory_type, content=memory_content, importance=2))
            created = True
    if created:
        db.commit()
