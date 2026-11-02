"""行程可执行性增强服务。

补充每日真实通勤时长、舒适度评估与备选方案,属于确定性收尾步骤。
"""

from __future__ import annotations

import time
from typing import Callable

from loguru import logger

from ..models.schemas import TripPlan, TripRequest
from ..domain.scheduler import build_day_timeline


def enrich_plan_execution_data(
    plan: TripPlan,
    request: TripRequest,
    emit: Callable[[str, str, str, float | None], None],
) -> TripPlan:
    """补充每日真实通勤时长、舒适度评估与备选方案。

    调用高德路线规划 API 计算相邻景点之间的真实距离与时长,
    生成 route_segments 供前端绘制交通时间轴;
    单点 API 失败时由 route_service 内部兜底估值,不影响整体流程。
    """
    from .route_service import calculate_day_routes, summarize_transit_minutes
    from .amap_service import get_amap_service

    start = time.time()
    emit("行程可执行性", "running", "正在调用高德路线规划计算每日真实通勤时长")
    amap = get_amap_service()
    total_segments = 0
    for day in plan.days:
        if not day.attractions:
            day.estimated_transit_minutes = 0
            day.route_segments = []
            day.plan_b = "如遇天气变化，建议通过 AI 对话重新安排当天景点。"
            day.comfort_level = "适中"
            day.timeline = build_day_timeline(day)
            continue
        # 模型生成的景点坐标经常是编造的(甚至不在本城市),统一按名称重新地理编码
        for attraction in day.attractions:
            try:
                attraction.location = amap.geocode_location(attraction.name, plan.city)
            except Exception as exc:
                logger.warning("geocode_failed name={} city={} error={}", attraction.name, plan.city, str(exc))
        try:
            segments = calculate_day_routes(
                attractions=day.attractions,
                city=plan.city,
                transportation=day.transportation or request.transportation,
            )
            day.route_segments = segments
            day.estimated_transit_minutes = summarize_transit_minutes(segments)
            total_segments += len(segments)
        except Exception as exc:
            logger.warning("route_calc_failed day={} error={}", day.day_index + 1, str(exc))
            day.estimated_transit_minutes = max(len(day.attractions) - 1, 0) * 20
            day.route_segments = []

        total_visit_minutes = sum(max(attraction.visit_duration or 0, 0) for attraction in day.attractions)
        total_minutes = total_visit_minutes + day.estimated_transit_minutes
        day.comfort_level = "轻松" if total_minutes <= 360 else "适中" if total_minutes <= 540 else "紧凑"

        rain_sensitive_names = "、".join(attraction.name for attraction in day.attractions[:2])
        day.plan_b = (
            f"如遇降雨或拥挤，可优先保留室内场馆，并通过 AI 对话将 {rain_sensitive_names} 替换为附近室内景点。"
            if day.attractions
            else "如遇天气变化，建议通过 AI 对话重新安排当天景点。"
        )
        day.timeline = build_day_timeline(day)
    emit(
        "行程可执行性",
        "success",
        f"已补充{len(plan.days)}天的真实通勤数据,共生成{total_segments}条路段",
        start,
    )
    return plan
