"""统一的并行任务执行器。

只负责线程调度与步骤事件,不关心任务内部调用的是 Agent 还是本地计算。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class ParallelTask:
    key: str
    name: str
    summary: str
    run: Callable[[], Any]


@dataclass(frozen=True)
class TaskOutcome:
    key: str
    value: Any = ""
    error: str = ""


def _brief(value: Any) -> str:
    """把任意返回值压缩成可展示的短文本。"""
    if isinstance(value, str):
        return value[:180]
    if isinstance(value, list):
        return f"返回{len(value)}条结果"
    return str(value)[:180]


def run_parallel(
    tasks: Sequence[ParallelTask],
    emit: Callable[[str, str, str, float | None], None],
) -> list[TaskOutcome]:
    """并行执行任务,按完成顺序返回结果,并同步推送 running/success/failed 事件。"""
    outcomes: list[TaskOutcome] = []
    started_at: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {}
        for task in tasks:
            started_at[task.key] = time.time()
            emit(task.name, "running", task.summary)
            futures[executor.submit(task.run)] = task
        for future in as_completed(futures):
            task = futures[future]
            try:
                value = future.result()
                outcomes.append(TaskOutcome(key=task.key, value=value))
                emit(task.name, "success", _brief(value), started_at[task.key])
            except Exception as exc:
                outcomes.append(TaskOutcome(key=task.key, error=str(exc)))
                emit(task.name, "failed", str(exc), started_at[task.key])
    return outcomes
