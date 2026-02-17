from __future__ import annotations

from .backends.relational import RelationalBackend

# Legacy compatibility alias.
# The active backend contract is RelationalBackend.
StorageBackend = RelationalBackend

__all__ = ["StorageBackend"]
