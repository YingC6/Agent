"""智能体运行时的薄封装。

只做 SimpleAgent 的配置化装配与统一 run/stream 出口,不重写 ReAct 循环,
避免行为漂移。
"""

from __future__ import annotations

from typing import Any, Iterator

from hello_agents import SimpleAgent

from ..services.llm_service import get_llm


class AgentRuntime:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: Any = None,
        tools: list[Any] | None = None,
        reset_history: bool = False,
    ):
        self.name = name
        self.agent = SimpleAgent(name=name, llm=llm or get_llm(), system_prompt=system_prompt)
        for tool in tools or []:
            self.agent.add_tool(tool)
        self.reset_history = reset_history

    def _prepare(self) -> None:
        """一次性调用场景清空历史,避免跨请求上下文串扰。"""
        if self.reset_history:
            self.agent.clear_history()

    def run(self, prompt: str) -> str:
        self._prepare()
        return self.agent.run(prompt)

    def stream(self, prompt: str) -> Iterator[str]:
        self._prepare()
        stream = getattr(self.agent, "stream_run", None)
        if not callable(stream):
            response = self.agent.run(prompt)
            for index in range(0, len(response), 24):
                yield response[index:index + 24]
            return
        for chunk in stream(prompt):
            text = str(chunk)
            if text:
                yield text

    def list_tools(self) -> list[Any]:
        return self.agent.list_tools()
