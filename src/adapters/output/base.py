from __future__ import annotations

from typing import Protocol

from ...schemas.observation import Observation


class OutputAdapter(Protocol):
    target_session_key: str | None = None

    async def send(self, obs: Observation) -> None:
        """Send one observation to an external output channel."""
        ...
