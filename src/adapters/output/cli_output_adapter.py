from __future__ import annotations

from ...schemas.observation import MessagePayload, Observation


class CliOutputAdapter:
    """Output adapter for CLI/terminal with session-key prefix."""

    def __init__(self, *, target_session_key: str | None = None) -> None:
        self.target_session_key = target_session_key

    async def send(self, obs: Observation) -> None:
        if self.target_session_key and obs.session_key != self.target_session_key:
            return
        text = self._extract_text(obs)
        session_key = obs.session_key or ""
        prefix = f"[{session_key}]" if session_key else "[session]"
        print(f"{prefix} {text}")

    @staticmethod
    def _extract_text(obs: Observation) -> str:
        payload = obs.payload
        if isinstance(payload, MessagePayload):
            return payload.text or ""
        return str(payload)
