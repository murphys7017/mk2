from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml

from .types import Scene, GateAction, BudgetSpec


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
class BudgetThresholdsConfig:
    high_score: float = 0.75
    medium_score: float = 0.50


@dataclass
class BudgetProfileConfig:
    budget_level: Literal["tiny", "normal", "deep"] = "normal"
    time_ms: int = 1500
    max_tokens: int = 512
    max_parallel: int = 2
    evidence_allowed: bool = True
    max_tool_calls: int = 1
    can_search_kb: bool = True
    can_call_tools: bool = True
    auto_clarify: bool = False
    fallback_mode: bool = False

    def to_budget_spec(self) -> BudgetSpec:
        return BudgetSpec(
            budget_level=self.budget_level,
            time_ms=self.time_ms,
            max_tokens=self.max_tokens,
            max_parallel=self.max_parallel,
            evidence_allowed=self.evidence_allowed,
            max_tool_calls=self.max_tool_calls,
            can_search_kb=self.can_search_kb,
            can_call_tools=self.can_call_tools,
            auto_clarify=self.auto_clarify,
            fallback_mode=self.fallback_mode,
        )


def _default_budget_profiles() -> Dict[str, BudgetProfileConfig]:
    return {
        "tiny": BudgetProfileConfig(
            budget_level="tiny",
            time_ms=800,
            max_tokens=256,
            max_parallel=1,
            evidence_allowed=False,
            max_tool_calls=0,
            can_search_kb=True,
            can_call_tools=True,
            auto_clarify=True,
        ),
        "normal": BudgetProfileConfig(
            budget_level="normal",
            time_ms=1500,
            max_tokens=512,
            max_parallel=2,
            evidence_allowed=True,
            max_tool_calls=1,
        ),
        "deep": BudgetProfileConfig(
            budget_level="deep",
            time_ms=3000,
            max_tokens=1024,
            max_parallel=4,
            evidence_allowed=True,
            max_tool_calls=3,
        ),
    }


@dataclass
class GateConfig:
    version: int = 1
    drop_escalation: DropEscalationConfig = field(default_factory=DropEscalationConfig)
    scene_policies: Dict[Scene, ScenePolicy] = field(default_factory=dict)
    rules: GateRulesConfig = field(default_factory=GateRulesConfig)
    overrides: OverridesConfig = field(default_factory=OverridesConfig)
    budget_thresholds: BudgetThresholdsConfig = field(default_factory=BudgetThresholdsConfig)
    budget_profiles: Dict[str, BudgetProfileConfig] = field(default_factory=_default_budget_profiles)

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

    def budget_profile(self, level: str) -> BudgetProfileConfig:
        profile = self.budget_profiles.get(level)
        if profile is not None:
            return profile
        return _default_budget_profiles().get(level, _default_budget_profiles()["normal"])

    def budget_for_level(self, level: str) -> BudgetSpec:
        return self.budget_profile(level).to_budget_spec()

    def select_budget(self, score: float, scene: Scene) -> BudgetSpec:
        if scene == Scene.ALERT:
            level = "deep"
        elif scene == Scene.TOOL_CALL:
            level = "normal"
        elif scene == Scene.TOOL_RESULT:
            level = "tiny"
        else:
            if score >= self.budget_thresholds.high_score:
                level = "deep"
            elif score >= self.budget_thresholds.medium_score:
                level = "normal"
            else:
                level = "tiny"

        budget = self.budget_for_level(level)

        # scene-specific safety clamps
        if scene == Scene.TOOL_RESULT:
            budget.can_search_kb = False
            budget.can_call_tools = False
            budget.evidence_allowed = False
            budget.max_tool_calls = 0

        if scene == Scene.DIALOGUE and budget.budget_level == "tiny":
            budget.auto_clarify = True

        return budget

    def with_overrides(self, **kwargs: Any) -> "GateConfig":
        new_overrides = replace(self.overrides, **{
            k: v for k, v in kwargs.items() if hasattr(self.overrides, k) and v is not None
        })
        if new_overrides == self.overrides:
            return self
        return replace(self, overrides=new_overrides)

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

        # budget thresholds
        bt = data.get("budget_thresholds", {}) or {}
        high_score = float(bt.get("high_score", cfg.budget_thresholds.high_score))
        medium_score = float(bt.get("medium_score", cfg.budget_thresholds.medium_score))
        if medium_score > high_score:
            medium_score = high_score
        cfg.budget_thresholds = BudgetThresholdsConfig(
            high_score=high_score,
            medium_score=medium_score,
        )

        # budget profiles
        default_profiles = _default_budget_profiles()
        raw_profiles = data.get("budget_profiles", {}) or {}
        parsed_profiles: Dict[str, BudgetProfileConfig] = {}

        for level, base in default_profiles.items():
            raw = raw_profiles.get(level, {}) or {}
            budget_level_val = raw.get("budget_level", base.budget_level)
            if isinstance(budget_level_val, str):
                budget_level_val = budget_level_val.strip().lower()
            parsed_profiles[level] = BudgetProfileConfig(
                budget_level=budget_level_val,  # type: ignore
                time_ms=int(raw.get("time_ms", base.time_ms)),
                max_tokens=int(raw.get("max_tokens", base.max_tokens)),
                max_parallel=int(raw.get("max_parallel", base.max_parallel)),
                evidence_allowed=bool(raw.get("evidence_allowed", base.evidence_allowed)),
                max_tool_calls=int(raw.get("max_tool_calls", base.max_tool_calls)),
                can_search_kb=bool(raw.get("can_search_kb", base.can_search_kb)),
                can_call_tools=bool(raw.get("can_call_tools", base.can_call_tools)),
                auto_clarify=bool(raw.get("auto_clarify", base.auto_clarify)),
                fallback_mode=bool(raw.get("fallback_mode", base.fallback_mode)),
            )

        cfg.budget_profiles = parsed_profiles

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
