from __future__ import annotations

from collections import deque
from typing import List

from .interfaces import GatePool
from ...schemas.observation import Observation


class DropPool(GatePool):
    def __init__(self, maxlen: int = 200) -> None:
        self._buf = deque(maxlen=maxlen)

    def ingest(self, obs: Observation) -> None:
        self._buf.append(obs)

    def recent(self, limit: int = 20) -> List[Observation]:
        return list(self._buf)[-limit:]
