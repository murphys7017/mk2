from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from ..schemas.observation import Observation


class GateAction(str, Enum):
    DROP = "drop"
    SINK = "sink"
    DELIVER = "deliver"


class Scene(str, Enum):
    DIALOGUE = "dialogue"
    GROUP = "group"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ALERT = "alert"
    UNKNOWN = "unknown"


@dataclass
class GateDecision:
    action: GateAction
    scene: Scene
    session_key: str
    target_worker: Optional[str] = None
    model_tier: Optional[str] = None
    response_policy: Optional[str] = None
    tool_policy: Optional[Dict[str, Any]] = None
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    fingerprint: Optional[str] = None


@dataclass
class GateOutcome:
    decision: GateDecision
    emit: List[Observation] = field(default_factory=list)
    ingest: List[Observation] = field(default_factory=list)


@dataclass
class GateContext:
    now: datetime
    config: "GateConfig"
    system_session_key: str
    metrics: Optional["GateMetrics"] = None
    session_state: Any = None
    system_health: Optional[Dict[str, Any]] = None


@dataclass
class GateWip:
    scene: Optional[Scene] = None
    features: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    fingerprint: Optional[str] = None

    action_hint: Optional[GateAction] = None
    model_tier: Optional[str] = None
    response_policy: Optional[str] = None
    tool_policy: Optional[Dict[str, Any]] = None

    emit: List[Observation] = field(default_factory=list)
    ingest: List[Observation] = field(default_factory=list)


class GateStage(Protocol):
    def apply(self, obs: Observation, ctx: GateContext, wip: GateWip) -> None: ...


if TYPE_CHECKING:
    from .config import GateConfig
    from .metrics import GateMetrics
