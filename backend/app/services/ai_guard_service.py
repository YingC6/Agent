"""AI生成保护服务"""

import hashlib
import json
from ..config import get_settings
from ..models.schemas import TripPlan, TripRequest
from .cache_service import cache_get, cache_set, rate_limit_check


def build_plan_cache_key(request: TripRequest, user_id: int | None = None) -> str:
    payload = {
        "user_id": user_id,
        "city": request.city,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "travel_days": request.travel_days,
        "transportation": request.transportation,
        "accommodation": request.accommodation,
        "preferences": sorted(request.preferences),
        "free_text_input": request.free_text_input or ""
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"ai_plan:{digest}"


def get_cached_plan(request: TripRequest, user_id: int | None = None) -> TripPlan | None:
    cached = cache_get(build_plan_cache_key(request, user_id))
    if not cached:
        return None
    return TripPlan(**cached)


def set_cached_plan(request: TripRequest, plan: TripPlan, user_id: int | None = None) -> None:
    settings = get_settings()
    cache_set(build_plan_cache_key(request, user_id), plan.model_dump(), settings.ai_plan_cache_ttl_seconds)


def check_plan_rate_limit(user_id: int | None, client_key: str = "anonymous") -> tuple[bool, int]:
    settings = get_settings()
    identity = f"user:{user_id}" if user_id else f"guest:{client_key}"
    key = f"rate_limit:plan:{identity}"
    return rate_limit_check(key, settings.plan_rate_limit_count, settings.plan_rate_limit_window_seconds)
