from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class ReflexConfig:
    # existing (placeholder defaults)
    burst_window_sec: float = 60.0
    burst_trigger_count: int = 5
    recovery_window_sec: float = 60.0
    min_emergency_hold_sec: float = 30.0
    transition_cooldown_sec: float = 5.0

    # agent suggestion
    allow_agent_suggestions: bool = True
    suggestion_ttl_default_sec: int = 60
    suggestion_cooldown_sec: int = 5

    # whitelist
    agent_override_whitelist: tuple[str, ...] = ("force_low_model",)


@dataclass
class SuggestionState:
    active_until_ts: float | None = None
    last_applied_ts: float | None = None
    active_overrides: Dict[str, object] = field(default_factory=dict)
