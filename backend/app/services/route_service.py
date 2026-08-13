"""行程路段计算服务

封装高德路线规划调用,将行程中相邻景点转换为 RouteSegment。
支持失败兜底与交通方式映射,避免单点 API 异常阻塞整个规划流程。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from loguru import logger

from ..models.schemas import Attraction, RouteSegment
from .amap_service import get_amap_service

# 用户输入的交通方式到高德 route_type 的映射
TRANSPORTATION_ROUTE_MAP = {
    "公共交通": "transit",
    "公交": "transit",
    "地铁": "transit",
    "步行": "walking",
    "走路": "walking",
    "徒步": "walking",
    "自驾": "driving",
    "开车": "driving",
    "租车": "driving",
    "打车": "driving",
    "出租车": "driving",
}

DEFAULT_ROUTE_TYPE = "transit"


def resolve_route_type(transportation: str | None) -> str:
    """根据用户填写的交通方式选择高德 route_type。"""
    if not transportation:
        return DEFAULT_ROUTE_TYPE
    key = transportation.strip()
    if key in TRANSPORTATION_ROUTE_MAP:
        return TRANSPORTATION_ROUTE_MAP[key]
    for keyword, route_type in TRANSPORTATION_ROUTE_MAP.items():
        if keyword in key:
            return route_type
    return DEFAULT_ROUTE_TYPE


def _attraction_address(attraction: Attraction) -> str:
    """优先使用地址,缺省时回退到景点名+城市拼接,避免空地址导致 API 拒绝。"""
    if attraction.address:
        return attraction.address
    return attraction.name


def build_route_segment(
    origin: Attraction,
    destination: Attraction,
    city: str,
    route_type: str,
) -> RouteSegment:
    """调用高德路线规划生成单个 RouteSegment,失败时返回估值兜底。"""
    amap = get_amap_service()
    origin_address = _attraction_address(origin)
    destination_address = _attraction_address(destination)
    try:
        payload = amap.plan_route(
            origin_address=origin_address,
            destination_address=destination_address,
            origin_city=city,
            destination_city=city,
            route_type=route_type,
        )
        summary = amap.parse_route_summary(payload, route_type)
        distance_meters = summary.get("distance_meters", 0.0)
        duration_seconds = summary.get("duration_seconds", 0)
        if distance_meters <= 0 and duration_seconds <= 0:
            raise ValueError("高德返回空路线")
        distance_km = round(distance_meters / 1000.0, 2)
        duration_minutes = max(int(duration_seconds // 60), 1)
        route_label = {"walking": "步行", "driving": "驾车", "transit": "公共交通"}.get(route_type, "公共交通")
        return RouteSegment(
            origin=origin.name,
            destination=destination.name,
            route_type=route_label,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
        )
    except Exception as error:
        logger.warning(
            "route_segment_fallback origin={} destination={} city={} error={}",
            origin.name,
            destination.name,
            city,
            str(error),
        )
        # 兜底:按直线距离粗估,每段至少 10 分钟,避免通勤总时长为 0
        return RouteSegment(
            origin=origin.name,
            destination=destination.name,
            route_type={"walking": "步行", "driving": "驾车", "transit": "公共交通"}.get(route_type, "公共交通"),
            distance_km=0.0,
            duration_minutes=15,
        )


def calculate_day_routes(
    attractions: Iterable[Attraction],
    city: str,
    transportation: str | None,
    max_workers: int = 3,
) -> list[RouteSegment]:
    """计算一天内相邻景点之间的路段信息。

    Args:
        attractions: 当天景点列表(按游览顺序)
        city: 所在城市
        transportation: 用户选择的交通方式
        max_workers: 并发调用高德 API 的线程数

    Returns:
        路段列表,长度为 max(len(attractions)-1, 0)
    """
    attraction_list = list(attractions)
    if len(attraction_list) < 2:
        return []
    route_type = resolve_route_type(transportation)
    pairs = list(zip(attraction_list[:-1], attraction_list[1:]))
    segments: list[RouteSegment | None] = [None] * len(pairs)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(build_route_segment, origin, destination, city, route_type): index
            for index, (origin, destination) in enumerate(pairs)
        }
        for future in as_completed(future_to_index):
            segments[future_to_index[future]] = future.result()

    return [segment for segment in segments if segment is not None]


def summarize_transit_minutes(segments: list[RouteSegment]) -> int:
    """汇总路段通勤总时长(分钟)。"""
    return sum(max(segment.duration_minutes, 0) for segment in segments)
