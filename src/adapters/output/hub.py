from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Mapping

from ...schemas.observation import Observation
from .base import OutputAdapter


class EgressHub:
    """Aggregate output adapters with optional session-key routing."""

    def __init__(
        self,
        adapters: Iterable[OutputAdapter] | None = None,
        *,
        session_adapters: Mapping[str, Iterable[OutputAdapter]] | None = None,
    ) -> None:
        self.adapters: List[OutputAdapter] = list(adapters or [])
        self.session_adapters: Dict[str, List[OutputAdapter]] = defaultdict(list)
        if session_adapters:
            for session_key, target_adapters in session_adapters.items():
                self.session_adapters[session_key].extend(list(target_adapters))

    def bind_session(self, session_key: str, adapter: OutputAdapter) -> None:
        self.session_adapters[session_key].append(adapter)

    def _resolve_adapters(self, obs: Observation) -> List[OutputAdapter]:
        session_key = obs.session_key or ""
        if session_key in self.session_adapters:
            return self.session_adapters[session_key]
        return self.adapters

    async def dispatch(self, obs: Observation) -> None:
        for adapter in self._resolve_adapters(obs):
            await adapter.send(obs)
