from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import Scene, GateContext, GateWip
from ..schemas.observation import Observation, ObservationType, MessagePayload, AlertPayload, SchedulePayload, WorldDataPayload


@dataclass
class SceneInferencer:
    """根据 Observation 推断 scene"""

    def apply(self, obs: Observation, ctx: GateContext, wip: GateWip) -> None:
        if obs.obs_type == ObservationType.ALERT:
            wip.scene = Scene.ALERT
            return
        if obs.obs_type in (ObservationType.SCHEDULE, ObservationType.SYSTEM, ObservationType.CONTROL):
            wip.scene = Scene.SYSTEM
            return
        if obs.obs_type == ObservationType.MESSAGE:
            # group vs dialogue 由 payload/actor/mentions 轻量判断
            if isinstance(obs.payload, MessagePayload):
                text = (obs.payload.text or "").strip()
                if "@" in text:
                    wip.scene = Scene.GROUP
                else:
                    wip.scene = Scene.DIALOGUE
            else:
                wip.scene = Scene.DIALOGUE
            return
        if obs.obs_type == ObservationType.WORLD_DATA:
            wip.scene = Scene.TOOL_RESULT
            return

        wip.scene = Scene.UNKNOWN
