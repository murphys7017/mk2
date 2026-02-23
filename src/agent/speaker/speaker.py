"""Speaker：将文本转为 Observation(MESSAGE)。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from ...schemas.observation import (
    Actor,
    MessagePayload,
    Observation,
    ObservationType,
    SourceKind,
)
from ..types import AgentRequest


class Speaker(Protocol):
    """Speaker 接口。"""

    def speak(
        self,
        req: AgentRequest,
        final_text: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Observation:
        ...


class AgentSpeaker:
    """Phase 0 默认 Speaker。"""

    source_name = "agent:speaker"
    actor_id = "agent"

    def speak(
        self,
        req: AgentRequest,
        final_text: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Observation:
        metadata = dict(extra or {})
        return Observation(
            obs_type=ObservationType.MESSAGE,
            source_name=self.source_name,
            source_kind=SourceKind.INTERNAL,
            session_key=req.obs.session_key,
            actor=Actor(actor_id=self.actor_id, actor_type="system", display_name="Agent"),
            payload=MessagePayload(text=final_text),
            metadata=metadata,
        )
