"""无工具智能体的单例注册表。

同一角色复用同一个 AgentRuntime,避免每次请求重复构造;
带 MCP 工具的智能体不使用注册表,必须各自持有独立工具实例以保证线程安全。
"""

from __future__ import annotations

import threading

from .runtime import AgentRuntime

_AGENTS: dict[str, AgentRuntime] = {}
_LOCK = threading.Lock()


def get_agent(key: str, name: str, system_prompt: str) -> AgentRuntime:
    with _LOCK:
        runtime = _AGENTS.get(key)
        if runtime is None:
            runtime = AgentRuntime(name=name, system_prompt=system_prompt, reset_history=True)
            _AGENTS[key] = runtime
        return runtime


def reset_agents() -> None:
    """清空注册表(用于测试或重新配置)。"""
    with _LOCK:
        _AGENTS.clear()
