from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...api.deps import get_current_admin, get_current_user, get_optional_user
from ...database import get_db
from ...models.db_models import PlaceCheckin, PlaceFavorite, PlacePost, PlaceReview, PostComment, PostLike, User
from ...services.amap_service import get_amap_service

router = APIRouter(prefix="/community", tags=["旅行社区"])


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    content: str = Field(default="", max_length=1000)


class CheckinRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class PostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    poi_id: str | None = Field(default=None, min_length=1, max_length=100)


class CommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class ModerationRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")


def format_time(value: datetime) -> str:
    return value.isoformat()


def get_poi_or_404(poi_id: str) -> dict:
    poi = get_amap_service().get_poi_detail(poi_id)
    if not poi:
        raise HTTPException(status_code=404, detail="高德 POI 不存在或暂时不可用")
    return poi


def poi_interaction_summary(poi_id: str, db: Session, user_id: int | None = None) -> dict:
    rating, review_count = db.execute(
        select(func.coalesce(func.avg(PlaceReview.rating), 0), func.count(PlaceReview.id)).where(PlaceReview.poi_id == poi_id)
    ).one()
    favorite_count = db.scalar(select(func.count(PlaceFavorite.id)).where(PlaceFavorite.poi_id == poi_id)) or 0
    checkin_count = db.scalar(select(func.count(PlaceCheckin.id)).where(PlaceCheckin.poi_id == poi_id)) or 0
    return {
        "rating": round(float(rating), 1),
        "review_count": review_count,
        "favorite_count": favorite_count,
        "checkin_count": checkin_count,
        "is_favorited": bool(user_id and db.scalar(select(PlaceFavorite.id).where(PlaceFavorite.poi_id == poi_id, PlaceFavorite.user_id == user_id))),
        "is_checked_in": bool(user_id and db.scalar(select(PlaceCheckin.id).where(PlaceCheckin.poi_id == poi_id, PlaceCheckin.user_id == user_id))),
    }


def post_to_dict(post: PlacePost, nickname: str, db: Session, user_id: int | None = None, include_comments: bool = False) -> dict:
    like_count = db.scalar(select(func.count(PostLike.id)).where(PostLike.post_id == post.id)) or 0
    comment_count = db.scalar(select(func.count(PostComment.id)).where(PostComment.post_id == post.id, PostComment.status == "approved")) or 0
    data = {
        "id": post.id,
        "poi_id": post.poi_id,
        "content": post.content,
        "status": post.status,
        "author": nickname,
        "created_at": format_time(post.created_at),
        "updated_at": format_time(post.updated_at),
        "like_count": like_count,
        "comment_count": comment_count,
        "is_liked": bool(user_id and db.scalar(select(PostLike.id).where(PostLike.post_id == post.id, PostLike.user_id == user_id))),
    }
    if include_comments:
        rows = db.execute(
            select(PostComment, User.nickname)
            .join(User, User.id == PostComment.user_id)
            .where(PostComment.post_id == post.id, PostComment.status == "approved")
            .order_by(PostComment.created_at.asc())
        ).all()
        data["comments"] = [{"id": item.id, "content": item.content, "author": name, "created_at": format_time(item.created_at)} for item, name in rows]
    return data


def get_post_or_404(post_id: int, db: Session) -> PlacePost:
    post = db.get(PlacePost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return post


@router.get("/pois/search")
def search_pois(
    keywords: str = Query(..., min_length=1, max_length=100),
    city: str | None = Query(default=None, max_length=80),
    citylimit: bool = Query(default=True),
):
    return {"success": True, "message": "查询成功", "data": get_amap_service().search_poi_data(keywords, city, citylimit)}


@router.get("/pois/{poi_id}")
def get_poi(poi_id: str, current_user=Depends(get_optional_user), db: Session = Depends(get_db)):
    poi = get_poi_or_404(poi_id)
    reviews = db.execute(
        select(PlaceReview, User.nickname)
        .join(User, User.id == PlaceReview.user_id)
        .where(PlaceReview.poi_id == poi_id)
        .order_by(PlaceReview.updated_at.desc())
    ).all()
    return {
        "success": True,
        "message": "查询成功",
        "data": {
            **poi,
            "poi_id": poi_id,
            **poi_interaction_summary(poi_id, db, current_user.id if current_user else None),
            "reviews": [{"id": item.id, "rating": item.rating, "content": item.content, "author": name, "created_at": format_time(item.created_at)} for item, name in reviews],
        },
    }


@router.post("/pois/{poi_id}/favorite")
def toggle_favorite(poi_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    favorite = db.scalar(select(PlaceFavorite).where(PlaceFavorite.poi_id == poi_id, PlaceFavorite.user_id == current_user.id))
    if favorite:
        db.delete(favorite)
        message = "已取消收藏"
    else:
        db.add(PlaceFavorite(poi_id=poi_id, user_id=current_user.id))
        message = "已收藏"
    db.commit()
    return {"success": True, "message": message, "data": poi_interaction_summary(poi_id, db, current_user.id)}


@router.post("/pois/{poi_id}/checkin")
def checkin(poi_id: str, request: CheckinRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.scalar(select(PlaceCheckin).where(PlaceCheckin.poi_id == poi_id, PlaceCheckin.user_id == current_user.id))
    if record:
        record.note = request.note
        message = "打卡内容已更新"
    else:
        db.add(PlaceCheckin(poi_id=poi_id, user_id=current_user.id, note=request.note))
        message = "打卡成功"
    db.commit()
    return {"success": True, "message": message, "data": poi_interaction_summary(poi_id, db, current_user.id)}


@router.post("/pois/{poi_id}/reviews")
def save_review(poi_id: str, request: ReviewRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    review = db.scalar(select(PlaceReview).where(PlaceReview.poi_id == poi_id, PlaceReview.user_id == current_user.id))
    if not review:
        review = PlaceReview(poi_id=poi_id, user_id=current_user.id, rating=request.rating)
        db.add(review)
    review.rating = request.rating
    review.content = request.content
    db.commit()
    db.refresh(review)
    return {"success": True, "message": "评价已保存", "data": {"summary": poi_interaction_summary(poi_id, db, current_user.id), "review": {"id": review.id, "rating": review.rating, "content": review.content, "author": current_user.nickname, "created_at": format_time(review.created_at)}}}


@router.get("/posts")
def list_posts(
    poi_id: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    query = select(PlacePost, User.nickname).join(User, User.id == PlacePost.user_id).where(PlacePost.status == "approved")
    if poi_id:
        query = query.where(PlacePost.poi_id == poi_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(PlacePost.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"success": True, "message": "查询成功", "data": {"items": [post_to_dict(post, nickname, db, current_user.id if current_user else None) for post, nickname in rows], "total": total}}


@router.post("/posts")
def create_post(request: PostRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if request.poi_id:
        get_poi_or_404(request.poi_id)
    post = PlacePost(poi_id=request.poi_id, user_id=current_user.id, content=request.content)
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"success": True, "message": "帖子已提交审核", "data": {"id": post.id, "status": post.status}}


@router.get("/posts/{post_id}")
def get_post(post_id: int, current_user=Depends(get_optional_user), db: Session = Depends(get_db)):
    post = get_post_or_404(post_id, db)
    if post.status != "approved" and (not current_user or (current_user.id != post.user_id and current_user.role != "admin")):
        raise HTTPException(status_code=404, detail="帖子不存在")
    author = db.get(User, post.user_id)
    return {"success": True, "message": "查询成功", "data": post_to_dict(post, author.nickname, db, current_user.id if current_user else None, include_comments=True)}


@router.post("/posts/{post_id}/likes")
def toggle_like(post_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    post = get_post_or_404(post_id, db)
    if post.status != "approved":
        raise HTTPException(status_code=404, detail="帖子不存在")
    like = db.scalar(select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id))
    if like:
        db.delete(like)
        message = "已取消点赞"
    else:
        db.add(PostLike(post_id=post_id, user_id=current_user.id))
        message = "已点赞"
    db.commit()
    return {"success": True, "message": message}


@router.post("/posts/{post_id}/comments")
def create_comment(post_id: int, request: CommentRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    post = get_post_or_404(post_id, db)
    if post.status != "approved":
        raise HTTPException(status_code=404, detail="帖子不存在")
    comment = PostComment(post_id=post_id, user_id=current_user.id, content=request.content, status="approved")
    db.add(comment)
    db.commit()
    return {"success": True, "message": "评论已发布", "data": {"id": comment.id, "status": comment.status}}


@router.get("/admin/moderation/posts")
def list_pending_posts(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50), current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = select(PlacePost, User.nickname).join(User, User.id == PlacePost.user_id).where(PlacePost.status == "pending")
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(PlacePost.created_at.asc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"success": True, "message": "查询成功", "data": {"items": [post_to_dict(post, nickname, db) for post, nickname in rows], "total": total}}


@router.patch("/admin/moderation/posts/{post_id}")
def moderate_post(post_id: int, request: ModerationRequest, current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    post = get_post_or_404(post_id, db)
    post.status = request.status
    db.commit()
    return {"success": True, "message": "审核完成"}


@router.get("/admin/moderation/comments")
def list_pending_comments(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=50), current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    query = select(PostComment, User.nickname).join(User, User.id == PostComment.user_id).where(PostComment.status == "pending")
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(PostComment.created_at.asc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = [{"id": item.id, "post_id": item.post_id, "content": item.content, "author": nickname, "created_at": format_time(item.created_at)} for item, nickname in rows]
    return {"success": True, "message": "查询成功", "data": {"items": items, "total": total}}


@router.patch("/admin/moderation/comments/{comment_id}")
def moderate_comment(comment_id: int, request: ModerationRequest, current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    comment = db.get(PostComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    comment.status = request.status
    db.commit()
    return {"success": True, "message": "审核完成"}


@router.get("/admin/stats")
def community_stats(current_admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return {"success": True, "message": "查询成功", "data": {"posts": {"total": db.scalar(select(func.count(PlacePost.id))) or 0, "pending": db.scalar(select(func.count(PlacePost.id)).where(PlacePost.status == "pending")) or 0, "approved": db.scalar(select(func.count(PlacePost.id)).where(PlacePost.status == "approved")) or 0, "rejected": db.scalar(select(func.count(PlacePost.id)).where(PlacePost.status == "rejected")) or 0}, "comments": {"total": db.scalar(select(func.count(PostComment.id))) or 0, "pending": db.scalar(select(func.count(PostComment.id)).where(PostComment.status == "pending")) or 0, "approved": db.scalar(select(func.count(PostComment.id)).where(PostComment.status == "approved")) or 0, "rejected": db.scalar(select(func.count(PostComment.id)).where(PostComment.status == "rejected")) or 0}, "poi_interactions": {"favorites": db.scalar(select(func.count(PlaceFavorite.id))) or 0, "checkins": db.scalar(select(func.count(PlaceCheckin.id))) or 0, "reviews": db.scalar(select(func.count(PlaceReview.id))) or 0, "likes": db.scalar(select(func.count(PostLike.id))) or 0}}}
