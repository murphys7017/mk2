from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .types import Scene, GateAction


@dataclass
class DropEscalationConfig:
    burst_window_sec: float = 60.0
    burst_count_threshold: int = 5
    consecutive_threshold: int = 8
    cooldown_suggest_sec: float = 300.0


@dataclass
class OverridesConfig:
    emergency_mode: bool = False
    force_low_model: bool = False
    drop_sessions: list[str] = field(default_factory=list)
    deliver_sessions: list[str] = field(default_factory=list)
    drop_actors: list[str] = field(default_factory=list)
    deliver_actors: list[str] = field(default_factory=list)


@dataclass
class DialogueRulesConfig:
    weights: Dict[str, float] = field(default_factory=lambda: {
        "base": 0.10,
        "mention": 0.40,
        "question_mark": 0.15,
        "long_text": 0.10,
    })
    keywords: Dict[str, float] = field(default_factory=lambda: {
        "urgent": 0.30,
        "error": 0.25,
        "help": 0.15,
    })
    long_text_len: int = 300


@dataclass
class GroupRulesConfig:
    weights: Dict[str, float] = field(default_factory=lambda: {
        "base": 0.05,
        "mention": 0.60,
        "whitelist_actor": 0.25,
    })
    sample_rate: float = 0.02
    whitelist_actors: list[str] = field(default_factory=list)


@dataclass
class SystemRulesConfig:
    weights: Dict[str, float] = field(default_factory=lambda: {
        "base": 0.0,
    })


@dataclass
class GateRulesConfig:
    dialogue: DialogueRulesConfig = field(default_factory=DialogueRulesConfig)
    group: GroupRulesConfig = field(default_factory=GroupRulesConfig)
    system: SystemRulesConfig = field(default_factory=SystemRulesConfig)


@dataclass
class ScenePolicy:
    deliver_threshold: float = 0.7
    sink_threshold: float = 0.3
    default_action: GateAction = GateAction.SINK
    default_model_tier: Optional[str] = "low"
    default_response_policy: Optional[str] = "respond_now"
    dedup_window_sec: float = 30.0
    max_reasons: int = 6


@dataclass
class GateConfig:
    version: int = 1
    drop_escalation: DropEscalationConfig = field(default_factory=DropEscalationConfig)
    scene_policies: Dict[Scene, ScenePolicy] = field(default_factory=dict)
    rules: GateRulesConfig = field(default_factory=GateRulesConfig)
    overrides: OverridesConfig = field(default_factory=OverridesConfig)

    def scene_policy(self, scene: Scene) -> ScenePolicy:
        if scene in self.scene_policies:
            return self.scene_policies[scene]

        # 默认策略
        if scene == Scene.ALERT:
            return ScenePolicy(
                deliver_threshold=0.0,
                sink_threshold=0.0,
                default_action=GateAction.DELIVER,
                default_model_tier=None,
                default_response_policy=None,
            )
        if scene == Scene.SYSTEM:
            return ScenePolicy(default_action=GateAction.SINK, default_model_tier=None)
        if scene == Scene.TOOL_CALL:
            return ScenePolicy(default_action=GateAction.DELIVER, default_model_tier=None)
        if scene == Scene.TOOL_RESULT:
            return ScenePolicy(default_action=GateAction.SINK, default_model_tier=None)
        if scene == Scene.GROUP:
            return ScenePolicy(default_action=GateAction.SINK, default_model_tier="low")
        if scene == Scene.DIALOGUE:
            return ScenePolicy(default_action=GateAction.SINK, default_model_tier="low")

        return ScenePolicy()

    def get_policy(self, scene: Scene) -> ScenePolicy:
        return self.scene_policy(scene)

    @staticmethod
    def default() -> "GateConfig":
        return GateConfig()

    @staticmethod
    def _parse_action(value: Any) -> GateAction:
        if isinstance(value, GateAction):
            return value
        if isinstance(value, str):
            val = value.strip().lower()
            if val == "drop":
                return GateAction.DROP
            if val == "sink":
                return GateAction.SINK
            if val == "deliver":
                return GateAction.DELIVER
        return GateAction.SINK

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GateConfig":
        data: Dict[str, Any] = {}
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            if isinstance(raw, dict):
                data = raw

        version = data.get("version", 1)
        if version != 1:
            raise ValueError(f"Unsupported gate config version: {version}")

        cfg = cls(version=version)

        # drop escalation
        de = data.get("drop_escalation", {}) or {}
        cfg.drop_escalation = DropEscalationConfig(
            burst_window_sec=de.get("burst_window_sec", cfg.drop_escalation.burst_window_sec),
            burst_count_threshold=de.get("burst_count_threshold", cfg.drop_escalation.burst_count_threshold),
            consecutive_threshold=de.get("consecutive_threshold", cfg.drop_escalation.consecutive_threshold),
            cooldown_suggest_sec=de.get("cooldown_suggest_sec", cfg.drop_escalation.cooldown_suggest_sec),
        )

        # overrides
        ov = data.get("overrides", {}) or {}
        cfg.overrides = OverridesConfig(
            emergency_mode=bool(ov.get("emergency_mode", False)),
            force_low_model=bool(ov.get("force_low_model", False)),
            drop_sessions=list(ov.get("drop_sessions", []) or []),
            deliver_sessions=list(ov.get("deliver_sessions", []) or []),
            drop_actors=list(ov.get("drop_actors", []) or []),
            deliver_actors=list(ov.get("deliver_actors", []) or []),
        )

        # rules
        rules = data.get("rules", {}) or {}
        dlg = rules.get("dialogue", {}) or {}
        grp = rules.get("group", {}) or {}
        sysr = rules.get("system", {}) or {}

        cfg.rules = GateRulesConfig(
            dialogue=DialogueRulesConfig(
                weights=dlg.get("weights", cfg.rules.dialogue.weights),
                keywords=dlg.get("keywords", cfg.rules.dialogue.keywords),
                long_text_len=dlg.get("long_text_len", cfg.rules.dialogue.long_text_len),
            ),
            group=GroupRulesConfig(
                weights=grp.get("weights", cfg.rules.group.weights),
                sample_rate=grp.get("sample_rate", cfg.rules.group.sample_rate),
                whitelist_actors=grp.get("whitelist_actors", cfg.rules.group.whitelist_actors),
            ),
            system=SystemRulesConfig(
                weights=sysr.get("weights", cfg.rules.system.weights),
            ),
        )

        # scene policies
        sp = data.get("scene_policies", {}) or {}
        for key, val in sp.items():
            try:
                scene = Scene(key)
            except Exception:
                continue
            val = val or {}
            cfg.scene_policies[scene] = ScenePolicy(
                deliver_threshold=val.get("deliver_threshold", 0.7),
                sink_threshold=val.get("sink_threshold", 0.3),
                default_action=cls._parse_action(val.get("default_action", GateAction.SINK)),
                default_model_tier=val.get("default_model_tier", "low"),
                default_response_policy=val.get("default_response_policy", "respond_now"),
                dedup_window_sec=val.get("dedup_window_sec", 30.0),
                max_reasons=val.get("max_reasons", 6),
            )

        return cfg
