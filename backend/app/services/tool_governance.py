import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any
from loguru import logger


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    required_parameters: tuple[str, ...]
    timeout_seconds: int = 45
    retries: int = 1
    call_limit: int = 1


class ToolGovernance:
    def __init__(self, policies: list[ToolPolicy]):
        self.policies = {policy.name: policy for policy in policies}
        self.call_counts: dict[str, int] = {}

    def run_agent(self, tool_name: str, agent: Any, query: str) -> str:
        policy = self.policies[tool_name]
        self._validate_query(tool_name, query, policy)
        count = self.call_counts.get(tool_name, 0)
        if count >= policy.call_limit:
            raise RuntimeError(f"工具{tool_name}已达到调用上限")
        self.call_counts[tool_name] = count + 1
        last_error: Exception | None = None
        for attempt in range(policy.retries + 1):
            started_at = time.monotonic()
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    result = executor.submit(agent.run, query).result(timeout=policy.timeout_seconds)
                logger.info("tool_call name={} attempt={} duration_ms={} status=success", tool_name, attempt + 1, int((time.monotonic() - started_at) * 1000))
                return result
            except TimeoutError as error:
                last_error = RuntimeError(f"工具{tool_name}调用超时")
                logger.warning("tool_call name={} attempt={} duration_ms={} status=timeout", tool_name, attempt + 1, int((time.monotonic() - started_at) * 1000))
            except Exception as error:
                last_error = error
                logger.warning("tool_call name={} attempt={} duration_ms={} status=failed error={}", tool_name, attempt + 1, int((time.monotonic() - started_at) * 1000), str(error))
        raise last_error or RuntimeError(f"工具{tool_name}调用失败")

    def _validate_query(self, tool_name: str, query: str, policy: ToolPolicy) -> None:
        actual_name, parameters = self._extract_tool_call(query)
        if actual_name != tool_name:
            raise ValueError(f"工具请求不匹配: {actual_name}")
        missing = set(policy.required_parameters) - set(parameters)
        if missing:
            raise ValueError(f"工具{tool_name}缺少参数: {','.join(sorted(missing))}")
        invalid = [name for name in policy.required_parameters if not isinstance(parameters[name], str) or not parameters[name].strip()]
        if invalid:
            raise ValueError(f"工具{tool_name}参数不能为空: {','.join(invalid)}")

    @staticmethod
    def _extract_tool_call(query: str) -> tuple[str, dict[str, Any]]:
        json_match = re.search(r"\[TOOL_CALL_JSON:(\{.*?\})\]", query, re.DOTALL)
        if json_match:
            try:
                payload = json.loads(json_match.group(1))
            except json.JSONDecodeError as error:
                raise ValueError("工具调用JSON格式无效") from error
            if not isinstance(payload, dict):
                raise ValueError("工具调用JSON必须是对象")
            tool_name = payload.get("name")
            parameters = payload.get("arguments")
            if not isinstance(tool_name, str) or not isinstance(parameters, dict):
                raise ValueError("工具调用JSON必须包含name和arguments对象")
            return tool_name, parameters

        legacy_match = re.search(r"\[TOOL_CALL:([^:]+):([^\]]+)\]", query)
        if not legacy_match:
            raise ValueError("工具请求缺少标准调用格式")
        tool_name, raw_parameters = legacy_match.groups()
        parameters = {
            item.split("=", 1)[0].strip(): item.split("=", 1)[1].strip()
            for item in raw_parameters.split(",")
            if "=" in item
        }
        return tool_name, parameters
