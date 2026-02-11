from __future__ import annotations

import hashlib
from typing import Dict

from ..types import GateContext, GateWip, GateAction, Scene
from ..config import ScenePolicy
from ...schemas.observation import Observation, MessagePayload


class Deduplicator:
    """去重窗口（MVP）"""

    def __init__(self) -> None:
        self._last_seen: Dict[str, float] = {}

    def _fingerprint(self, obs: Observation, wip: GateWip) -> str:
        parts = [wip.scene.value if wip.scene else "unknown", obs.actor.actor_id or "unknown"]
        if isinstance(obs.payload, MessagePayload):
            text = (obs.payload.text or "").strip().lower()
            parts.append(text)
        else:
            parts.append(type(obs.payload).__name__)
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def apply(self, obs: Observation, ctx: GateContext, wip: GateWip) -> None:
        try:
            scene = wip.scene or Scene.UNKNOWN
            if scene == Scene.ALERT:
                return
            policy: ScenePolicy = ctx.config.get_policy(scene)

            fp = self._fingerprint(obs, wip)
            wip.fingerprint = fp

            now_ts = ctx.now.timestamp()
            last = self._last_seen.get(fp)
            if last is not None and (now_ts - last) <= policy.dedup_window_sec:
                wip.tags["dedup"] = "hit"
                wip.action_hint = GateAction.DROP
                wip.reasons.append("dedup_hit")
            self._last_seen[fp] = now_ts
        except Exception as e:
            wip.reasons.append(f"dedup_error:{e}")
