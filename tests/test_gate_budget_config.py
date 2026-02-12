from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.gate import DefaultGate, GateConfig, GateContext
from src.gate.types import Scene
from src.schemas.observation import (
    Actor,
    MessagePayload,
    Observation,
    ObservationType,
    WorldDataPayload,
)


def _ctx(gate: DefaultGate) -> GateContext:
    return GateContext(
        now=datetime.now(timezone.utc),
        config=gate.config,
        system_session_key="system",
        metrics=gate.metrics,
        session_state=None,
        system_health=None,
    )


def _make_user_message(text: str) -> Observation:
    return Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test_input",
        session_key="dm:test",
        actor=Actor(actor_id="u1", actor_type="user"),
        payload=MessagePayload(text=text),
    )


def test_gate_config_loads_budget_blocks(tmp_path: Path):
    path = tmp_path / "gate.yaml"
    path.write_text(
        """
version: 1
budget_thresholds:
  high_score: 0.91
  medium_score: 0.41
budget_profiles:
  tiny:
    time_ms: 111
    max_tokens: 222
    evidence_allowed: false
  normal:
    time_ms: 333
    max_tokens: 444
  deep:
    time_ms: 555
    max_tokens: 666
scene_policies: {}
""",
        encoding="utf-8",
    )

    cfg = GateConfig.from_yaml(path)
    assert cfg.budget_thresholds.high_score == 0.91
    assert cfg.budget_thresholds.medium_score == 0.41
    assert cfg.budget_profile("tiny").time_ms == 111
    assert cfg.budget_profile("normal").max_tokens == 444
    assert cfg.budget_profile("deep").time_ms == 555


def test_policy_uses_configured_budget_thresholds_and_profiles():
    cfg = GateConfig()
    cfg.budget_thresholds.high_score = 0.8
    cfg.budget_thresholds.medium_score = 0.2
    cfg.budget_profiles["tiny"].time_ms = 111
    cfg.budget_profiles["normal"].time_ms = 222
    cfg.budget_profiles["deep"].time_ms = 333

    gate = DefaultGate(config=cfg)

    low = gate.handle(_make_user_message("hi"), _ctx(gate))
    assert low.decision.scene == Scene.DIALOGUE
    assert low.decision.hint.budget.budget_level == "tiny"
    assert low.decision.hint.budget.time_ms == 111

    mid = gate.handle(_make_user_message("hello?"), _ctx(gate))
    assert mid.decision.hint.budget.budget_level == "normal"
    assert mid.decision.hint.budget.time_ms == 222

    high_text = ("urgent error help " * 20) + "?"
    high = gate.handle(_make_user_message(high_text), _ctx(gate))
    assert high.decision.hint.budget.budget_level == "deep"
    assert high.decision.hint.budget.time_ms == 333


def test_tool_result_budget_forces_no_tooling():
    cfg = GateConfig()
    cfg.budget_profiles["tiny"].can_search_kb = True
    cfg.budget_profiles["tiny"].can_call_tools = True
    cfg.budget_profiles["tiny"].evidence_allowed = True
    cfg.budget_profiles["tiny"].max_tool_calls = 2
    gate = DefaultGate(config=cfg)

    obs = Observation(
        obs_type=ObservationType.WORLD_DATA,
        source_name="tool",
        session_key="dm:test",
        actor=Actor(actor_id="tool", actor_type="service"),
        payload=WorldDataPayload(schema_id="test", data={"ok": True}),
    )
    out = gate.handle(obs, _ctx(gate))
    assert out.decision.scene == Scene.TOOL_RESULT
    assert out.decision.hint.budget.budget_level == "tiny"
    assert out.decision.hint.budget.can_search_kb is False
    assert out.decision.hint.budget.can_call_tools is False
    assert out.decision.hint.budget.evidence_allowed is False
    assert out.decision.hint.budget.max_tool_calls == 0
