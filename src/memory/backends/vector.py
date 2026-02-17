# memory/backends/vector.py
# =========================
# 向量索引（抽象 + 内存实现）
# =========================

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from typing import Optional, Protocol
from dataclasses import dataclass, field


# =============================================================================
# EmbeddingProvider 抽象
# =============================================================================

class EmbeddingProvider(ABC):
    """
    Embedding 提供者抽象
    
    负责将文本转换为向量
    """
    
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        将文本列表转换为向量列表
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表，每个向量是 float list
        """
        pass
    
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """
        将单个文本转换为向量
        """
        return self.embed_texts([text])[0]


# =============================================================================
# VectorIndex 抽象
# =============================================================================

@dataclass
class VectorSearchResult:
    """向量搜索结果"""
    id: str
    score: float
    metadata: dict


class VectorIndex(ABC):
    """
    向量索引抽象
    
    负责存储与检索向量
    """
    
    @abstractmethod
    def upsert(self, id: str, text: str, metadata: Optional[dict] = None) -> None:
        """
        插入或更新向量
        
        Args:
            id: 唯一标识
            text: 文本内容
            metadata: 元数据
        """
        pass
    
    @abstractmethod
    def delete(self, id: str) -> bool:
        """
        删除向量
        
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    def query(self, text: str, topk: int = 10, filters: Optional[dict] = None) -> list[VectorSearchResult]:
        """
        查询相似度最高的向量
        
        Args:
            text: 查询文本
            topk: 返回数量
            filters: 过滤条件（如 scope: "persona"）
            
        Returns:
            搜索结果列表
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空索引"""
        pass


# =============================================================================
# 确定性 Embedding（用于测试）
# =============================================================================

class DeterministicEmbeddingProvider(EmbeddingProvider):
    """
    确定性 Embedding 提供者
    
    基于文本的 hash，生成确定的向量
    用于离线测试和演示
    """
    
    def __init__(self, dim: int = 128):
        self.dim = dim
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """生成向量列表"""
        vectors = []
        for text in texts:
            vector = self._hash_to_vector(text)
            vectors.append(vector)
        return vectors
    
    def embed_text(self, text: str) -> list[float]:
        """生成单个向量"""
        return self._hash_to_vector(text)
    
    def _hash_to_vector(self, text: str) -> list[float]:
        """从文本 hash 生成向量"""
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        
        # 将 hash 分成多个部分，转换为 [0, 1] 范围的 float
        vector = []
        for i in range(self.dim):
            byte_index = i % len(hash_bytes)
            byte_value = hash_bytes[byte_index]
            # 规范化到 [0, 1]
            normalized = (byte_value + i * 7) % 256 / 256.0
            vector.append(normalized)
        
        # 规范化为单位向量
        magnitude = sum(v ** 2 for v in vector) ** 0.5
        if magnitude > 0:
            vector = [v / magnitude for v in vector]
        
        return vector


# =============================================================================
# 内存向量索引
# =============================================================================

@dataclass
class _VectorEntry:
    """内部向量条目"""
    id: str
    vector: list[float]
    metadata: dict
    text: str


class InMemoryVectorIndex(VectorIndex):
    """
    内存向量索引实现
    
    用于离线测试，不依赖外部向量库
    """
    
    def __init__(self, embedding_provider: Optional[EmbeddingProvider] = None):
        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider()
        self.entries: dict[str, _VectorEntry] = {}
    
    def upsert(self, id: str, text: str, metadata: Optional[dict] = None) -> None:
        """插入或更新向量"""
        metadata = metadata or {}
        vector = self.embedding_provider.embed_text(text)
        
        self.entries[id] = _VectorEntry(
            id=id,
            vector=vector,
            metadata=metadata,
            text=text,
        )
    
    def delete(self, id: str) -> bool:
        """删除向量"""
        if id in self.entries:
            del self.entries[id]
            return True
        return False
    
    def query(self, text: str, topk: int = 10, filters: Optional[dict] = None) -> list[VectorSearchResult]:
        """查询相似度最高的向量"""
        query_vector = self.embedding_provider.embed_text(text)
        
        # 计算与所有项的相似度
        similarities = []
        for entry in self.entries.values():
            # 检查 filters
            if filters:
                skip = False
                for key, value in filters.items():
                    if entry.metadata.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue
            
            # 组合向量相似度与轻量词法匹配，提升离线检索稳定性
            similarity = self._cosine_similarity(query_vector, entry.vector)
            similarity += self._lexical_boost(text, entry.text)
            similarities.append((entry, similarity))
        
        # 按相似度排序
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # 返回 topk 结果
        results = []
        for entry, score in similarities[:topk]:
            results.append(
                VectorSearchResult(
                    id=entry.id,
                    score=score,
                    metadata=entry.metadata,
                )
            )
        
        return results
    
    def clear(self) -> None:
        """清空索引"""
        self.entries.clear()
    
    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """计算两个向量的余弦相似度"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a ** 2 for a in vec1) ** 0.5
        magnitude2 = sum(b ** 2 for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)

    @staticmethod
    def _lexical_boost(query: str, text: str) -> float:
        """基于子串与词重叠的轻量加权。"""
        q = query.strip().casefold()
        t = text.strip().casefold()
        if not q or not t:
            return 0.0

        boost = 0.0
        if q in t:
            boost += 0.2

        q_tokens = set(re.findall(r"\w+", q))
        t_tokens = set(re.findall(r"\w+", t))
        if q_tokens and t_tokens:
            overlap = len(q_tokens & t_tokens) / len(q_tokens)
            boost += 0.15 * overlap

        return boost
