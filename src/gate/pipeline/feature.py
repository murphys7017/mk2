from __future__ import annotations

from ..types import GateContext, GateWip
from ..scene import Scene
from ...schemas.observation import Observation, ObservationType, MessagePayload, AlertPayload


class FeatureExtractor:
    """提取最小特征用于评分"""

    def apply(self, obs: Observation, ctx: GateContext, wip: GateWip) -> None:
        try:
            wip.features["obs_type"] = obs.obs_type.value
            wip.features["source_name"] = obs.source_name
            wip.features["actor_id"] = obs.actor.actor_id

            if obs.obs_type == ObservationType.MESSAGE and isinstance(obs.payload, MessagePayload):
                text = (obs.payload.text or "").strip()
                wip.features["text_len"] = len(text)
                wip.features["has_mention"] = "@" in text
                wip.features["has_bot_mention"] = "@bot" in text
                wip.features["has_question"] = "?" in text
            if obs.obs_type == ObservationType.ALERT and isinstance(obs.payload, AlertPayload):
                wip.features["alert_severity"] = obs.payload.severity
        except Exception as e:
            wip.reasons.append(f"feature_error:{e}")
