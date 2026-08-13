"""出行清单路由

提供出行清单的完整管理接口:
- GET    /api/trips/{trip_id}/checklist          查询清单
- POST   /api/trips/{trip_id}/checklist          添加清单条目
- POST   /api/trips/{trip_id}/checklist/generate AI 自动生成清单
- PUT    /api/checklist/{item_id}                更新条目(勾选/内容/分类)
- DELETE /api/checklist/{item_id}                删除条目
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...api.deps import get_current_user
from ...database import get_db
from ...models.db_models import TripRecord
from ...models.schemas import TripPlan
from ...services.checklist_service import (
    CATEGORIES,
    checklist_to_dict,
    create_checklist_item,
    delete_checklist_item,
    generate_checklist_with_ai,
    list_checklist,
    update_checklist_item,
)

router = APIRouter(tags=["出行清单"])


class ChecklistItemCreateRequest(BaseModel):
    category: str = Field(default="其他", description="分类: 证件/衣物/电子/药品/其他")
    content: str = Field(..., min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)


class ChecklistItemUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=200)
    is_checked: bool | None = None
    category: str | None = None


def _get_owned_trip(db: Session, trip_id: int, user_id: int) -> TripRecord:
    trip = db.get(TripRecord, trip_id)
    if not trip or trip.user_id != user_id:
        raise HTTPException(status_code=404, detail="行程不存在")
    return trip


@router.get("/trips/{trip_id}/checklist")
def get_checklist(trip_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """查询指定行程的出行清单。"""
    _get_owned_trip(db, trip_id, current_user.id)
    items = list_checklist(db, trip_id)
    # 按分类分组返回,方便前端展示
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(checklist_to_dict(item))
    return {
        "success": True,
        "message": "查询成功",
        "data": {
            "items": [checklist_to_dict(item) for item in items],
            "grouped": grouped,
            "total": len(items),
            "checked_count": sum(1 for item in items if item.is_checked),
        },
    }


@router.post("/trips/{trip_id}/checklist")
def add_checklist_item(trip_id: int, request: ChecklistItemCreateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """手动添加清单条目。"""
    _get_owned_trip(db, trip_id, current_user.id)
    if request.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"分类无效,可选: {','.join(CATEGORIES)}")
    item = create_checklist_item(db, trip_id, request.category, request.content, request.sort_order)
    return {"success": True, "message": "条目已添加", "data": checklist_to_dict(item)}


@router.post("/trips/{trip_id}/checklist/generate")
def generate_checklist(trip_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """AI 根据行程信息自动生成出行清单。

    已有条目不会被覆盖,仅追加缺失的条目。
    """
    trip = _get_owned_trip(db, trip_id, current_user.id)
    try:
        plan = TripPlan(**json.loads(trip.plan_json))
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"行程数据解析失败: {error}")
    created = generate_checklist_with_ai(db, trip, plan)
    return {
        "success": True,
        "message": f"已生成 {len(created)} 个清单条目",
        "data": [checklist_to_dict(item) for item in created],
    }


@router.put("/checklist/{item_id}")
def update_checklist(item_id: int, request: ChecklistItemUpdateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """更新清单条目(勾选状态/内容/分类)。"""
    from ...models.db_models import TripChecklist
    checklist_item = db.get(TripChecklist, item_id)
    if not checklist_item:
        raise HTTPException(status_code=404, detail="清单条目不存在")
    # 校验归属:通过 trip_id 查行程,确认属于当前用户
    trip = db.get(TripRecord, checklist_item.trip_id)
    if not trip or trip.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="清单条目不存在")
    if request.category is not None and request.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"分类无效,可选: {','.join(CATEGORIES)}")
    updated = update_checklist_item(db, item_id, request.content, request.is_checked, request.category)
    return {"success": True, "message": "条目已更新", "data": checklist_to_dict(updated)}


@router.delete("/checklist/{item_id}")
def delete_checklist(item_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """删除清单条目。"""
    from ...models.db_models import TripChecklist
    checklist_item = db.get(TripChecklist, item_id)
    if not checklist_item:
        raise HTTPException(status_code=404, detail="清单条目不存在")
    trip = db.get(TripRecord, checklist_item.trip_id)
    if not trip or trip.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="清单条目不存在")
    delete_checklist_item(db, item_id)
    return {"success": True, "message": "条目已删除"}
