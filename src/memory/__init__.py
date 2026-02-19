# memory/__init__.py
# =========================
# 记忆子系统（Memory Subsystem）
# 提供事件存储、对话历史、上下文记忆等能力
# =========================

from __future__ import annotations

from .models import (
    EventRecord,
    TurnRecord,
    MemoryItem,
    MemoryScope,
    ContextPack,
    SerializableMixin,
)
from .service import MemoryService
from .config import (
    MemoryConfig,
    MemoryConfigProvider,
)
from .backends import (
    SQLAlchemyBackend,
    MarkdownVaultHybrid,
    MarkdownVaultError,
    VectorIndex,
    EmbeddingProvider,
    InMemoryVectorIndex,
    DeterministicEmbeddingProvider,
)

__all__ = [
    # Models
    "EventRecord",
    "TurnRecord",
    "MemoryItem",
    "MemoryScope",
    "ContextPack",
    "SerializableMixin",
    # Vault
    "MarkdownVaultHybrid",
    "MarkdownVaultError",
    # Service
    "MemoryService",
    # Config
    "MemoryConfig",
    "MemoryConfigProvider",
    # Backends
    "SQLAlchemyBackend",
    "VectorIndex",
    "EmbeddingProvider",
    "InMemoryVectorIndex",
    "DeterministicEmbeddingProvider",
]

