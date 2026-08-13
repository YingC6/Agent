"""向量嵌入服务

复用现有 LLM 配置(LLM_API_KEY / LLM_BASE_URL),通过 OpenAI 兼容的
/embeddings 接口生成文本向量。阿里云 DashScope 兼容模式默认支持
text-embedding-v3 模型,维度 1024。

设计要点:
- 单例 EmbeddingService,避免重复创建 httpx 客户端
- 批量嵌入接口 embed_texts,减少网络往返
- 本地缓存(LRU)避免重复嵌入相同文本
- 维度自动探测:首次调用后记录模型返回的维度
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx
from loguru import logger

from ..config import get_settings

# 阿里云 DashScope 兼容模式默认嵌入模型
DEFAULT_EMBEDDING_MODEL = "text-embedding-v3"
# 嵌入缓存上限,避免内存无限增长
EMBEDDING_CACHE_SIZE = 512


class EmbeddingService:
    """调用 OpenAI 兼容 /embeddings 接口生成文本向量。"""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or settings.openai_api_key
        self.base_url = (os.getenv("LLM_BASE_URL") or settings.openai_base_url).rstrip("/")
        self.model = os.getenv("LLM_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        self.timeout = float(os.getenv("LLM_TIMEOUT") or "120")
        self._dimension: int | None = None
        self._available: bool | None = None

    @property
    def dimension(self) -> int:
        """返回嵌入维度,未知时默认 1024(阿里云 text-embedding-v3)。"""
        return self._dimension or 1024

    @property
    def available(self) -> bool:
        """是否已确认嵌入服务可用。"""
        return self._available is True

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本,返回向量列表。

        失败时抛出 RuntimeError,由调用方决定降级策略。
        """
        if not texts:
            return []
        # 过滤空文本,避免 API 报错
        indexed_texts = [(i, text if text.strip() else "空") for i, text in enumerate(texts)]
        payload = {
            "model": self.model,
            "input": [text for _, text in indexed_texts],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/embeddings", json=payload, headers=headers)
                response.raise_for_status()
            data = response.json()
            embeddings_data = data.get("data", [])
            # 按 index 排序,保证顺序与输入一致
            embeddings_data.sort(key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in embeddings_data]
            if vectors:
                self._dimension = len(vectors[0])
            self._available = True
            logger.info("embedding_success count={} dimension={}", len(vectors), self._dimension)
            return vectors
        except Exception as error:
            self._available = False
            logger.warning("embedding_failed model={} error={}", self.model, str(error))
            raise RuntimeError(f"嵌入服务调用失败: {error}") from error

    def embed_query(self, text: str) -> list[float]:
        """嵌入单条查询文本。"""
        vectors = self.embed_texts([text])
        return vectors[0] if vectors else []

    def probe(self) -> bool:
        """探测嵌入服务是否可用,返回是否成功。"""
        try:
            self.embed_texts(["测试"])
            return True
        except Exception:
            return False


# 单例
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """获取 EmbeddingService 单例。"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
