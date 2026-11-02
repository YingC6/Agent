"""LLM 文本输出的唯一 JSON 解析入口。

所有从模型回复中提取 JSON 的代码都必须经过这里,避免出现多套裁剪规则。
"""

from __future__ import annotations

import json
import re
from typing import Any


def _locate_payload(text: str) -> str | None:
    """按历史行为定位 JSON 文本:优先代码块,否则取首个 `{` 到最后一个 `}`。"""
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        return text[start:end]
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        return text[start:end]

    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group() if match else None


def extract_json(text: str) -> dict[str, Any]:
    """宽松解析:无 JSON 片段时按原文解析,保留旧调用方的兜底语义。"""
    payload = _locate_payload(text)
    if payload is None:
        payload = text
    return json.loads(payload.strip())


def parse_json_object(text: str) -> dict[str, Any]:
    """严格解析:未找到 JSON 片段直接报错,供行程主链路使用。"""
    payload = _locate_payload(text)
    if payload is None:
        raise ValueError("响应中未找到JSON数据")
    return json.loads(payload.strip())
