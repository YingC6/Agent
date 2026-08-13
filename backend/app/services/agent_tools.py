from typing import Any

from langchain_core.tools import tool

from .amap_service import get_amap_service


@tool("search_places", description="按城市和关键词查询真实地点。")
def search_places(city: str, keywords: str) -> list[dict[str, Any]]:
    return get_amap_service().search_poi_data(keywords, city)


@tool("estimate_route", description="估算两个地点之间的路线和通勤时间。")
def estimate_route(origin_address: str, destination_address: str, city: str, route_type: str = "transit") -> dict[str, Any]:
    return get_amap_service().plan_route(origin_address, destination_address, city, city, route_type)


@tool("estimate_budget", description="根据住宿、门票、餐饮和交通成本计算旅行预算。")
def estimate_budget(travel_days: int, hotel_cost_per_night: int, attraction_cost: int, meal_cost_per_day: int, transportation_cost_per_day: int) -> dict[str, int]:
    total_hotels = max(hotel_cost_per_night, 0) * max(travel_days, 1)
    total_meals = max(meal_cost_per_day, 0) * max(travel_days, 1)
    total_transportation = max(transportation_cost_per_day, 0) * max(travel_days, 1)
    total_attractions = max(attraction_cost, 0)
    return {
        "total_hotels": total_hotels,
        "total_meals": total_meals,
        "total_transportation": total_transportation,
        "total_attractions": total_attractions,
        "total": total_hotels + total_meals + total_transportation + total_attractions,
    }


TRAVEL_TOOLS = [search_places, estimate_route, estimate_budget]
