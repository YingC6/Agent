"""用户偏好管理路由

提供对 UserMemory 表的完整 CRUD:
- GET    /api/preferences          查询当前用户的所有偏好
- POST   /api/preferences          手动添加偏好(偏好/避开/预算)
- PUT    /api/preferences/{id}     更新偏好内容或重要度
- DELETE /api/preferences/{id}     删除偏好
- GET    /api/preferences/context  获取构建好的偏好上下文文本

偏好类型:
- preference: 用户喜欢的内容
- avoidance:  用户避开的内容
- budget:     预算约束
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from loguru import logger

from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import UserMemory
from ...services.memory_service import build_user_memory_context

router = APIRouter(prefix="/preferences", tags=["偏好管理"])

VALID_MEMORY_TYPES = {"preference", "avoidance", "budget"}


class PreferenceCreateRequest(BaseModel):
    memory_type: str = Field(..., description="偏好类型: preference/avoidance/budget")
    content: str = Field(..., min_length=2, max_length=500, description="偏好内容")
    importance: int = Field(default=2, ge=1, le=5, description="重要度 1-5")


class PreferenceUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=2, max_length=500)
    importance: int | None = Field(default=None, ge=1, le=5)


def _memory_to_dict(memory: UserMemory) -> dict:
    return {
        "id": memory.id,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "importance": memory.importance,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
    }


@router.get("")
def list_preferences(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """查询当前用户的所有偏好记忆,按重要度和更新时间排序。"""
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == current_user.id)
        .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
    )
    memories = list(db.scalars(stmt).all())
    return {"success": True, "message": "查询成功", "data": [_memory_to_dict(item) for item in memories]}


@router.get("/context")
def get_preference_context(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """获取构建好的偏好上下文文本,供前端展示或调试。"""
    context = build_user_memory_context(db, current_user.id)
    return {"success": True, "message": "查询成功", "data": {"context": context}}


@router.post("")
def create_preference(request: PreferenceCreateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """手动添加偏好记忆。

    自动为偏好类型添加前缀(偏好:/避开:/预算:),保持与
    remember_preferences_from_message 的格式一致。
    """
    if request.memory_type not in VALID_MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"偏好类型无效,可选: {','.join(VALID_MEMORY_TYPES)}")

    prefix = {"preference": "偏好", "avoidance": "避开", "budget": "预算"}[request.memory_type]
    content = f"{prefix}：{request.content.strip()}"

    exists = db.scalar(
        select(UserMemory).where(
            UserMemory.user_id == current_user.id,
            UserMemory.memory_type == request.memory_type,
            UserMemory.content == content,
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="该偏好已存在")

    memory = UserMemory(
        user_id=current_user.id,
        memory_type=request.memory_type,
        content=content,
        importance=request.importance,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    logger.info("preference_created user_id={} type={} id={}", current_user.id, request.memory_type, memory.id)
    return {"success": True, "message": "偏好已添加", "data": _memory_to_dict(memory)}


@router.put("/{memory_id}")
def update_preference(memory_id: int, request: PreferenceUpdateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """更新偏好内容或重要度。"""
    memory = db.get(UserMemory, memory_id)
    if not memory or memory.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="偏好不存在")

    if request.content is not None:
        prefix = {"preference": "偏好", "avoidance": "避开", "budget": "预算"}.get(memory.memory_type, "")
        memory.content = f"{prefix}：{request.content.strip()}" if prefix else request.content.strip()
    if request.importance is not None:
        memory.importance = request.importance
    db.commit()
    db.refresh(memory)
    return {"success": True, "message": "偏好已更新", "data": _memory_to_dict(memory)}


@router.delete("/{memory_id}")
def delete_preference(memory_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """删除偏好记忆。"""
    memory = db.get(UserMemory, memory_id)
    if not memory or memory.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="偏好不存在")
    db.delete(memory)
    db.commit()
    logger.info("preference_deleted user_id={} id={}", current_user.id, memory_id)
    return {"success": True, "message": "偏好已删除"}
