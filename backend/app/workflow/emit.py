"""统一的步骤事件发射器。

工作流节点、规划 Agent 阶段方法、知识检索进度都通过它向前端推送 SSE 步骤。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from loguru import logger


class StepEmitter:
    """封装步骤事件构造、结构化日志与 progress_callback 转发。"""

    def __init__(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        run_id: str = "",
        log_steps: bool = True,
    ):
        self.progress_callback = progress_callback
        self.run_id = run_id
        self.log_steps = log_steps
        self.steps: list[dict[str, Any]] = []

    def __call__(
        self,
        name: str,
        status: str,
        summary: str = "",
        started_at: float | None = None,
    ) -> None:
        step: dict[str, Any] = {
            "name": name,
            "status": status,
            "summary": summary,
            "duration_ms": int((time.time() - started_at) * 1000) if started_at else 0,
        }
        if self.run_id:
            step = {"run_id": self.run_id, **step, "timestamp_ms": int(time.time() * 1000)}
        self.steps.append(step)
        if self.log_steps and self.run_id:
            logger.info(
                "workflow_step run_id={} node={} status={} duration_ms={} summary={}",
                self.run_id,
                name,
                status,
                step["duration_ms"],
                summary[:180],
            )
        if self.progress_callback:
            self.progress_callback(step)
