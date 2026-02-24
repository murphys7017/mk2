"""Context types for Agent Phase 1.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ...schemas.observation import Observation


@dataclass
class ContextSlot:
    """Single context slot value with priority metadata."""

    name: str
    value: Any
    priority: int
    source: str
    status: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextPack:
    """Context pack for agent processing."""

    slots: Dict[str, ContextSlot] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    # Backward-compatible fields for existing pools/trace.
    recent_obs: List[Observation] = field(default_factory=list)
    slots_hit: Dict[str, bool] = field(default_factory=dict)


@dataclass
class SlotSpec:
    """Slot configuration and default behaviors."""

    name: str
    provider: str
    default_priority: int
    required_by_default: bool = False
    enabled: bool = True


@dataclass
class ProviderResult:
    """Provider output used by the ContextBuilder."""

    slot_name: str
    value: Any = None
    status: str = "ok"
    meta: Dict[str, Any] = field(default_factory=dict)
    error: str | None = None
