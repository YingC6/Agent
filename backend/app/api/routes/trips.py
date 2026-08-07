"""历史行程路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import TripRecord
from ...services.knowledge_service import rate_trip
from ...services.trip_repository import list_trip_records, trip_to_dict

router = APIRouter(prefix="/trips", tags=["历史行程"])


class RatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=500)


@router.get("")
def list_trips(keyword: str | None = Query(default=None), page: int = Query(default=1, ge=1), page_size: int = Query(default=10, ge=1, le=50), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    items, total = list_trip_records(db, current_user.id, keyword, page, page_size)
    return {"success": True, "message": "查询成功", "data": {"items": [trip_to_dict(item) for item in items], "total": total}}


@router.get("/{trip_id}")
def get_trip(trip_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.get(TripRecord, trip_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="行程不存在")
    return {"success": True, "message": "查询成功", "data": trip_to_dict(record)}


@router.post("/{trip_id}/rating")
def rate_trip_record(trip_id: int, request: RatingRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.get(TripRecord, trip_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="行程不存在")
    rating = rate_trip(db, record, current_user.id, request.rating, request.comment)
    return {"success": True, "message": "评分成功", "data": {"id": rating.id, "trip_id": rating.trip_id, "rating": rating.rating, "comment": rating.comment}}


@router.delete("/{trip_id}")
def delete_trip(trip_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.get(TripRecord, trip_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="行程不存在")
    db.delete(record)
    db.commit()
    return {"success": True, "message": "删除成功"}
