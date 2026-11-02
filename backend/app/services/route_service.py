"""行程路段计算服务

封装高德路线规划调用,将行程中相邻景点转换为 RouteSegment。
支持失败兜底与交通方式映射,避免单点 API 异常阻塞整个规划流程。
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from loguru import logger

from ..models.schemas import Attraction, Location, RouteSegment
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


def haversine_km(origin: Location, destination: Location) -> float:
    """计算两个经纬度之间的直线距离(公里)。"""
    lat1 = math.radians(origin.latitude)
    lat2 = math.radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(destination.longitude - origin.longitude)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


MIN_TRUSTED_DISTANCE_KM = 0.05


def _resolve_locations(amap, origin: Attraction, destination: Attraction, city: str) -> tuple[Location, Location]:
    """两个不同景点的坐标几乎重合时,视为模型坐标不可信,按名称重新地理编码。"""
    if haversine_km(origin.location, destination.location) >= MIN_TRUSTED_DISTANCE_KM:
        return origin.location, destination.location
    resolved: list[Location] = []
    for attraction in (origin, destination):
        try:
            resolved.append(amap.geocode_location(attraction.name, city))
        except Exception:
            resolved.append(attraction.location)
    return resolved[0], resolved[1]


def build_route_segment(
    origin: Attraction,
    destination: Attraction,
    city: str,
    route_type: str,
) -> RouteSegment:
    """调用高德路线规划生成单个 RouteSegment,失败时返回估值兜底。"""
    amap = get_amap_service()
    origin_location, destination_location = _resolve_locations(amap, origin, destination, city)
    try:
        # 景点本身带经纬度,直接按坐标规划,省去地址再解析且避免 MCP 大响应阻塞
        payload = amap.plan_route_by_location(origin_location, destination_location, city, route_type)
        summary = amap.parse_route_summary(payload, route_type)
        distance_meters = summary.get("distance_meters", 0.0)
        duration_seconds = summary.get("duration_seconds", 0)
        # 距离为 0 说明坐标无效或路线为空,不能直接展示成 "0 km"
        if distance_meters <= 0:
            raise ValueError("高德返回无效路线")
        distance_km = round(distance_meters / 1000.0, 2)
        duration_minutes = max(int(duration_seconds // 60), 1)
        route_path = amap.parse_route_path(payload, route_type)
        if len(route_path) < 2:
            route_path = [[origin_location.longitude, origin_location.latitude], [destination_location.longitude, destination_location.latitude]]
        route_label = {"walking": "步行", "driving": "驾车", "transit": "公共交通"}.get(route_type, "公共交通")
        return RouteSegment(
            origin=origin.name,
            destination=destination.name,
            route_type=route_label,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            path=route_path,
        )
    except Exception as error:
        logger.warning(
            "route_segment_fallback origin={} destination={} city={} error={}",
            origin.name,
            destination.name,
            city,
            str(error),
        )
        # 兜底:按直线距离粗估,不同景点至少显示 0.1 km,避免再次出现 0 km
        distance_km = haversine_km(origin_location, destination_location)
        if origin.name != destination.name:
            distance_km = max(distance_km, 0.1)
        distance_km = round(distance_km, 2)
        minutes_per_km = {"walking": 13, "driving": 2, "transit": 8}.get(route_type, 8)
        wait_minutes = 5 if route_type == "transit" else 0
        duration_minutes = max(1, int(round(distance_km * minutes_per_km + wait_minutes)))
        route_path = [[origin_location.longitude, origin_location.latitude], [destination_location.longitude, destination_location.latitude]]
        return RouteSegment(
            origin=origin.name,
            destination=destination.name,
            route_type={"walking": "步行", "driving": "驾车", "transit": "公共交通"}.get(route_type, "公共交通"),
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            path=route_path,
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
