"""旅行知识库路由"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ...api.deps import get_current_admin, get_current_user
from ...database import get_db
from ...models.db_models import KnowledgeItem
from ...models.schemas import TripRequest
from ...services.knowledge_service import import_markdown_knowledge, knowledge_to_dict, search_relevant_knowledge

router = APIRouter(prefix="/knowledge", tags=["旅行知识库"])


class MarkdownImportRequest(BaseModel):
    markdown: str = Field(..., min_length=10)


@router.post("/import-markdown")
def import_markdown(request: MarkdownImportRequest, current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    item = import_markdown_knowledge(db, request.markdown, current_admin.id)
    return {"success": True, "message": "导入成功", "data": knowledge_to_dict(item)}


@router.get("")
def list_knowledge(city: str | None = Query(default=None), source: str | None = Query(default=None), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(KnowledgeItem).order_by(KnowledgeItem.created_at.desc())
    if city:
        stmt = stmt.where(KnowledgeItem.city == city)
    if source:
        stmt = stmt.where(KnowledgeItem.source == source)
    items = db.scalars(stmt).all()
    return {"success": True, "message": "查询成功", "data": [knowledge_to_dict(item) for item in items]}


@router.post("/search")
def search_knowledge(request: TripRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    items = search_relevant_knowledge(db, request)
    return {"success": True, "message": "检索成功", "data": [knowledge_to_dict(item) for item in items]}


@router.delete("/{knowledge_id}")
def delete_knowledge(knowledge_id: int, current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    item = db.get(KnowledgeItem, knowledge_id)
    if not item:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    db.delete(item)
    db.commit()
    return {"success": True, "message": "删除成功"}
