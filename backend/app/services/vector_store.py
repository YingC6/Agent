"""FAISS 向量存储与检索

管理知识库分块的向量索引,支持:
- 批量构建索引(build_index):将知识条目分块、嵌入并写入 FAISS
- 语义检索(search):根据查询向量返回 top-k 最相似分块
- 增量更新(upsert_items):知识库变更时重建索引
- 内存缓存:索引常驻内存,避免每次检索重建

索引结构:
- FAISS IndexFlatIP(内积相似度,向量预先 L2 归一化)
- id_map:FAISS 索引位置 → KnowledgeChunk 元数据
- 维度由 embedding_service 动态探测,默认 1024

降级策略:
- 嵌入服务不可用时,build_index 返回空索引,search 返回空列表
- 调用方(knowledge_service)回退到规则检索
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger

from ..models.db_models import KnowledgeItem
from .embedding_service import get_embedding_service
from .knowledge_service import KnowledgeChunk, split_knowledge_chunks

# 每个知识条目最多保留的分块数,控制索引规模
MAX_CHUNKS_PER_ITEM = 3
# 默认检索返回数量
DEFAULT_TOP_K = 8


@dataclass
class VectorSearchResult:
    """向量检索结果。"""
    chunk: KnowledgeChunk
    score: float


@dataclass
class _VectorStoreState:
    """向量存储内部状态,受锁保护。"""
    index: Any = None  # faiss.Index
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    dimension: int = 0
    built_at: float = 0.0
    item_ids: set[int] = field(default_factory=set)
    item_fingerprints: dict[int, str] = field(default_factory=dict)


class VectorStore:
    """FAISS 向量存储单例,管理知识库向量索引的生命周期。"""

    def __init__(self) -> None:
        self._state = _VectorStoreState()
        self._lock = threading.Lock()
        self._embedding = get_embedding_service()

    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        """L2 归一化,使内积等价于余弦相似度。"""
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vectors / norms).astype(np.float32)

    def build_index(self, items: list[KnowledgeItem]) -> bool:
        """构建 FAISS 索引。

        将每个知识条目分块、批量嵌入、L2 归一化后写入 IndexFlatIP。
        返回是否构建成功(嵌入服务不可用时返回 False)。
        """
        try:
            import faiss
        except ImportError:
            logger.warning("vector_store_build failed: faiss not installed")
            return False

        # 收集所有分块
        all_chunks: list[KnowledgeChunk] = []
        item_fingerprints = {
            item.id: hashlib.sha256(
                f"{item.title}\n{item.city}\n{item.days}\n{item.themes}\n{item.keywords}\n{item.content}".encode("utf-8")
            ).hexdigest()
            for item in items
        }
        for item in items:
            chunks = split_knowledge_chunks(item)[:MAX_CHUNKS_PER_ITEM]
            all_chunks.extend(chunks)

        if not all_chunks:
            logger.info("vector_store_build skipped: no chunks")
            with self._lock:
                self._state.index = None
                self._state.chunks = []
                self._state.item_ids = {item.id for item in items}
                self._state.item_fingerprints = item_fingerprints
                self._state.built_at = time.time()
            return True

        # 批量嵌入
        texts = [chunk.content for chunk in all_chunks]
        try:
            vectors = self._embedding.embed_texts(texts)
        except RuntimeError as error:
            logger.warning("vector_store_build failed: {}", str(error))
            return False

        vector_matrix = np.array(vectors, dtype=np.float32)
        if vector_matrix.shape[0] != len(all_chunks):
            logger.warning(
                "vector_store_build mismatch: chunks={} vectors={}",
                len(all_chunks),
                vector_matrix.shape[0],
            )
            return False

        normalized = self._normalize(vector_matrix)
        dimension = normalized.shape[1]

        # 构建 FAISS 内积索引(向量已归一化,内积=余弦相似度)
        index = faiss.IndexFlatIP(dimension)
        index.add(normalized)

        with self._lock:
            self._state.index = index
            self._state.chunks = all_chunks
            self._state.dimension = dimension
            self._state.item_ids = {item.id for item in items}
            self._state.item_fingerprints = item_fingerprints
            self._state.built_at = time.time()

        logger.info(
            "vector_store_build success: items={} chunks={} dimension={}",
            len(items),
            len(all_chunks),
            dimension,
        )
        return True

    def search(self, query_text: str, top_k: int = DEFAULT_TOP_K) -> list[VectorSearchResult]:
        """向量检索:返回与查询文本最相似的 top_k 个分块。"""
        with self._lock:
            index = self._state.index
            chunks = list(self._state.chunks)

        if index is None or not chunks:
            return []

        try:
            query_vector = self._embedding.embed_query(query_text)
        except RuntimeError:
            return []

        if not query_vector:
            return []

        query_array = np.array([query_vector], dtype=np.float32)
        query_normalized = self._normalize(query_array)
        k = min(top_k, len(chunks))
        scores, indices = index.search(query_normalized, k)

        results: list[VectorSearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(chunks):
                continue
            results.append(VectorSearchResult(chunk=chunks[idx], score=float(score)))
        return results

    def needs_rebuild(self, items: list[KnowledgeItem] | set[int]) -> bool:
        """检查索引是否需要重建(知识条目集合或内容变化时)。"""
        with self._lock:
            if isinstance(items, set):
                return self._state.item_ids != items
            current_ids = {item.id for item in items}
            if self._state.item_ids != current_ids:
                return True
            current_fingerprints = {
                item.id: hashlib.sha256(
                    f"{item.title}\n{item.city}\n{item.days}\n{item.themes}\n{item.keywords}\n{item.content}".encode("utf-8")
                ).hexdigest()
                for item in items
            }
            return self._state.item_fingerprints != current_fingerprints

    @property
    def is_ready(self) -> bool:
        """索引是否已构建且可用。"""
        with self._lock:
            return self._state.index is not None and len(self._state.chunks) > 0

    @property
    def chunk_count(self) -> int:
        with self._lock:
            return len(self._state.chunks)


# 单例
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """获取 VectorStore 单例。"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
