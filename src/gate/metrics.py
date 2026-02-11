from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class GateMetrics:
    processed_total: int = 0
    dropped_total: int = 0
    sunk_total: int = 0
    delivered_total: int = 0

    by_scene: Dict[str, int] = field(default_factory=dict)
    by_action: Dict[str, int] = field(default_factory=dict)

    def inc_scene(self, scene: str) -> None:
        self.by_scene[scene] = self.by_scene.get(scene, 0) + 1

    def inc_action(self, action: str) -> None:
        self.by_action[action] = self.by_action.get(action, 0) + 1
