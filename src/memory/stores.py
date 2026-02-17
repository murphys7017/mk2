from __future__ import annotations

from typing import Protocol

from .backends.relational import RelationalBackend

# Legacy compatibility aliases.
# Event/Turn storage now follows the unified RelationalBackend contract.
EventStore = RelationalBackend
TurnStore = RelationalBackend


class MemoryStore(Protocol):
    """Reserved skeleton for future memory-item store abstraction."""


__all__ = ["EventStore", "TurnStore", "MemoryStore"]
