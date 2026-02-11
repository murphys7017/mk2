from __future__ import annotations

from typing import Protocol, List

from ...schemas.observation import Observation


class GatePool(Protocol):
    def ingest(self, obs: Observation) -> None: ...
    def recent(self, limit: int = 20) -> List[Observation]: ...
