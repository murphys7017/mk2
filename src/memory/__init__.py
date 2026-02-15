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
    ContextPack,
    SerializableMixin,
)
from .stores import (
    EventStore,
    TurnStore,
    MemoryStore,
)
from .backend import (
    StorageBackend,
)
from .service import (
    MemoryService,
)

__all__ = [
    # Models
    "EventRecord",
    "TurnRecord",
    "MemoryItem",
    "ContextPack",
    "SerializableMixin",
    # Stores
    "EventStore",
    "TurnStore",
    "MemoryStore",
    # Backend
    "StorageBackend",
    # Service
    "MemoryService",
]
