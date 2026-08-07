"""高德地图MCP服务封装"""

import json
import re
from typing import Any, Dict, List, Optional

from hello_agents.tools import MCPTool

from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo

_amap_mcp_tool = None


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
            server_command=["uvx", "amap-mcp-server"],
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
        self.mcp_tool = get_amap_mcp_tool()

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

    def plan_route(self, origin_address: str, destination_address: str, origin_city: Optional[str] = None, destination_city: Optional[str] = None, route_type: str = "walking") -> Dict[str, Any]:
        tool_name = {"walking": "maps_direction_walking_by_address", "driving": "maps_direction_driving_by_address", "transit": "maps_direction_transit_integrated_by_address"}.get(route_type, "maps_direction_walking_by_address")
        arguments = {"origin_address": origin_address, "destination_address": destination_address}
        if origin_city:
            arguments["origin_city"] = origin_city
        if destination_city:
            arguments["destination_city"] = destination_city
        return self._call(tool_name, arguments)

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
