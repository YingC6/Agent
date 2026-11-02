"""高德地图服务封装

POI/天气等查询仍走高德 MCP;路线规划改走高德 Web 服务 REST 接口,
避免 MCP stdio 在返回大体积路线数据时阻塞或崩溃。
"""

import json
import re
from typing import Any, Dict, List, Optional

import httpx
from hello_agents.tools import MCPTool

from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo

AMAP_REST_BASE = "https://restapi.amap.com/v3"

_amap_mcp_tool = None


def amap_rest_get(path: str, params: Dict[str, str]) -> Dict[str, Any]:
    """调用高德 Web 服务接口,固定超时避免线程被无限阻塞。"""
    settings = get_settings()
    if not settings.amap_api_key:
        raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
    with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
        response = client.get(f"{AMAP_REST_BASE}{path}", params={**params, "key": settings.amap_api_key})
        response.raise_for_status()
        payload = response.json()
    if str(payload.get("status")) != "1":
        raise ValueError(payload.get("info") or "高德接口返回异常")
    return payload


def get_amap_mcp_tool() -> MCPTool:
    global _amap_mcp_tool
    if _amap_mcp_tool is None:
        settings = get_settings()
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        env_vars = {"AMAP_MAPS_API_KEY": settings.amap_api_key}
        if settings.amap_security_key:
            env_vars["AMAP_SECURITY_KEY"] = settings.amap_security_key
        _amap_mcp_tool = MCPTool(
            name="amap",
            description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
            # uvx 默认会解析到最新 pydantic,与 amap-mcp-server 依赖的 mcp 1.x 不兼容
            server_command=["uvx", "--with", "pydantic<2.11", "amap-mcp-server"],
            env=env_vars,
            auto_expand=True,
        )
    return _amap_mcp_tool


def parse_mcp_result(result: Any) -> Any:
    if isinstance(result, (dict, list)):
        return result
    if not isinstance(result, str):
        return {}
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", result)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}


def find_poi_items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("pois", "data", "results", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = find_poi_items(value)
            if nested:
                return nested
    return []


def normalize_poi(item: dict) -> dict:
    location = item.get("location") or item.get("lnglat") or item.get("location_info") or ""
    if isinstance(location, str):
        longitude, _, latitude = location.partition(",")
        location = {"longitude": longitude, "latitude": latitude}
    elif isinstance(location, (list, tuple)) and len(location) >= 2:
        location = {"longitude": location[0], "latitude": location[1]}
    elif not isinstance(location, dict):
        location = {}
    longitude = location.get("longitude", location.get("lng", ""))
    latitude = location.get("latitude", location.get("lat", ""))
    return {
        "poi_id": str(item.get("id") or item.get("poi_id") or ""),
        "name": item.get("name", ""),
        "type": item.get("type") or item.get("typecode") or "",
        "address": item.get("address", ""),
        "location": {"longitude": longitude, "latitude": latitude},
        "tel": item.get("tel") or item.get("telephone") or "",
        "city": item.get("cityname") or item.get("city") or "",
        "photos": item.get("photos") or [],
    }


class AmapService:
    def __init__(self):
        # MCP 只在真正用到 POI/天气时才启动,路线走 REST 不需要拉起子进程
        self._mcp_tool: Optional[MCPTool] = None

    @property
    def mcp_tool(self) -> MCPTool:
        if self._mcp_tool is None:
            self._mcp_tool = get_amap_mcp_tool()
        return self._mcp_tool

    def _call(self, tool_name: str, arguments: dict) -> Any:
        return parse_mcp_result(self.mcp_tool.run({"action": "call_tool", "tool_name": tool_name, "arguments": arguments}))

    def search_poi_data(self, keywords: str, city: str | None = None, citylimit: bool = True) -> list[dict]:
        arguments = {"keywords": keywords, "citylimit": str(citylimit).lower()}
        if city:
            arguments["city"] = city
        payload = self._call("maps_text_search", arguments)
        return [poi for poi in (normalize_poi(item) for item in find_poi_items(payload)) if poi["poi_id"]]

    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        pois = self.search_poi_data(keywords, city, citylimit)
        result = []
        for poi in pois:
            try:
                result.append(POIInfo(
                    id=poi["poi_id"],
                    name=poi["name"],
                    type=poi["type"],
                    address=poi["address"],
                    location=Location(longitude=float(poi["location"]["longitude"]), latitude=float(poi["location"]["latitude"])),
                    tel=poi["tel"] or None,
                ))
            except (TypeError, ValueError):
                continue
        return result

    def get_weather(self, city: str) -> List[WeatherInfo]:
        return []

    ROUTE_PATHS = {
        "walking": "/direction/walking",
        "driving": "/direction/driving",
        "transit": "/direction/transit/integrated",
    }

    def geocode_location(self, address: str, city: Optional[str] = None) -> Location:
        """通过高德地理编码接口把地址转成经纬度。"""
        params = {"address": address}
        if city:
            params["city"] = city
        payload = amap_rest_get("/geocode/geo", params)
        geocodes = payload.get("geocodes") or []
        location_text = (geocodes[0] or {}).get("location", "") if geocodes else ""
        parts = str(location_text).split(",")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"高德无法解析地址: {address}")
        return Location(longitude=float(parts[0]), latitude=float(parts[1]))

    def plan_route_by_location(
        self,
        origin: Location,
        destination: Location,
        city: str,
        route_type: str = "walking",
    ) -> Dict[str, Any]:
        """按经纬度规划路线,走 REST 接口,不经过 MCP stdio。"""
        path = self.ROUTE_PATHS.get(route_type, self.ROUTE_PATHS["walking"])
        params = {
            "origin": f"{origin.longitude},{origin.latitude}",
            "destination": f"{destination.longitude},{destination.latitude}",
            "extensions": "base",
        }
        if route_type == "transit":
            params.update({"city": city, "cityd": city})
        return amap_rest_get(path, params)

    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> Dict[str, Any]:
        city = origin_city or destination_city or ""
        origin = self.geocode_location(origin_address, origin_city)
        destination = self.geocode_location(destination_address, destination_city)
        return self.plan_route_by_location(origin, destination, city, route_type)

    def parse_route_path(self, payload: Any, route_type: str = "walking") -> List[List[float]]:
        """从高德路线响应中提取折线坐标,供前端绘制真实路线。"""
        points: List[List[float]] = []
        if not isinstance(payload, dict):
            return points
        route_node = payload.get("route") or {}

        def add_polyline(polyline: Any) -> None:
            for pair in str(polyline or "").split(";"):
                longitude, _, latitude = pair.partition(",")
                try:
                    points.append([float(longitude), float(latitude)])
                except ValueError:
                    continue

        if route_type == "transit":
            for transit in (route_node.get("transits") or [])[:1]:
                for segment in transit.get("segments") or []:
                    for step in (segment.get("walking") or {}).get("steps") or []:
                        add_polyline(step.get("polyline"))
                    for busline in (segment.get("bus") or {}).get("buslines") or []:
                        add_polyline(busline.get("polyline"))
        else:
            for path in (route_node.get("paths") or [])[:1]:
                for step in path.get("steps") or []:
                    add_polyline(step.get("polyline"))
        return points

    def parse_route_summary(self, payload: Any, route_type: str = "walking") -> Dict[str, Any]:
        """从高德路线规划响应中提取距离与时长摘要。

        Returns:
            {"distance_meters": float, "duration_seconds": int, "route_type": str}
            解析失败时返回零值摘要,避免阻塞主流程。
        """
        summary = {"distance_meters": 0.0, "duration_seconds": 0, "route_type": route_type}
        if not isinstance(payload, dict):
            return summary
        route_node = payload.get("route") or {}
        if route_type == "transit":
            transits = route_node.get("transits") or []
            if transits and isinstance(transits, list):
                first = transits[0] if isinstance(transits[0], dict) else {}
                summary["distance_meters"] = float(first.get("distance") or 0)
                summary["duration_seconds"] = int(float(first.get("duration") or 0))
        else:
            paths = route_node.get("paths") or []
            if paths and isinstance(paths, list):
                first = paths[0] if isinstance(paths[0], dict) else {}
                summary["distance_meters"] = float(first.get("distance") or 0)
                summary["duration_seconds"] = int(float(first.get("duration") or 0))
        return summary

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        arguments = {"address": address}
        if city:
            arguments["city"] = city
        payload = self._call("maps_geo", arguments)
        poi = normalize_poi(payload if isinstance(payload, dict) else {})
        try:
            return Location(longitude=float(poi["location"]["longitude"]), latitude=float(poi["location"]["latitude"]))
        except (TypeError, ValueError):
            return None

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        payload = self._call("maps_search_detail", {"id": poi_id})
        if isinstance(payload, dict):
            for key in ("poi", "data", "result"):
                if isinstance(payload.get(key), dict):
                    payload = payload[key]
                    break
        if not isinstance(payload, dict):
            return {}
        poi = normalize_poi(payload)
        poi["poi_id"] = poi_id
        return poi if poi["name"] or poi["address"] else {}


_amap_service = None


def get_amap_service() -> AmapService:
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service
