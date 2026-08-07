"""生成日志路由"""

import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import GenerationLog

router = APIRouter(prefix="/logs", tags=["生成日志"])


@router.get("")
def list_logs(page: int = Query(default=1, ge=1), page_size: int = Query(default=10, ge=1, le=50), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(GenerationLog).where(GenerationLog.user_id == current_user.id).order_by(GenerationLog.created_at.desc())
    total = len(db.scalars(stmt).all())
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    data = []
    for item in items:
        data.append({
            "id": item.id,
            "trip_id": item.trip_id,
            "city": item.city,
            "status": item.status,
            "steps": json.loads(item.steps_json),
            "error_message": item.error_message,
            "duration_ms": item.duration_ms,
            "created_at": item.created_at.isoformat()
        })
    return {"success": True, "message": "查询成功", "data": {"items": data, "total": total}}
