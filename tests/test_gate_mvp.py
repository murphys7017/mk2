from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.gate import DefaultGate, GateContext, GateConfig
from src.schemas.observation import Observation, ObservationType, Actor, MessagePayload


def _make_message_obs(text: str, session_key: str = "dm:test") -> Observation:
    return Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="text_input",
        session_key=session_key,
        actor=Actor(actor_id="u1", actor_type="user"),
        payload=MessagePayload(text=text),
    )


def _ctx(gate: DefaultGate, now: datetime, system_health=None):
    return GateContext(
        now=now,
        config=gate.config,
        system_session_key="system",
        metrics=gate.metrics,
        session_state=None,
        system_health=system_health,
    )


def test_scene_dialogue_infer():
    gate = DefaultGate()
    obs = _make_message_obs("hello")
    ctx = _ctx(gate, datetime.now(timezone.utc))
    outcome = gate.handle(obs, ctx)
    assert outcome.decision.scene.value == "dialogue"


def test_group_default_sink():
    gate = DefaultGate()
    obs = _make_message_obs("hello @someone")
    ctx = _ctx(gate, datetime.now(timezone.utc))
    outcome = gate.handle(obs, ctx)
    assert outcome.decision.action.value == "sink"


def test_group_mention_deliver():
    gate = DefaultGate()
    obs = _make_message_obs("@bot please help")
    ctx = _ctx(gate, datetime.now(timezone.utc))
    outcome = gate.handle(obs, ctx)
    assert outcome.decision.action.value == "deliver"


def test_dedup_hit_drop():
    gate = DefaultGate()
    obs = _make_message_obs("hello dedup")
    now = datetime.now(timezone.utc)

    ctx1 = _ctx(gate, now)
    _ = gate.handle(obs, ctx1)

    ctx2 = _ctx(gate, now + timedelta(seconds=1))
    outcome2 = gate.handle(obs, ctx2)

    assert outcome2.decision.action.value == "drop"
    assert outcome2.decision.tags.get("dedup") == "hit"


def test_drop_burst_alert():
    cfg = GateConfig()
    cfg.drop_escalation.burst_count_threshold = 2
    cfg.drop_escalation.consecutive_threshold = 2

    gate = DefaultGate(config=cfg)
    now = datetime.now(timezone.utc)

    # 空内容触发 DROP + 连续 drop
    obs1 = _make_message_obs("")
    obs2 = _make_message_obs("")

    outcome1 = gate.handle(obs1, _ctx(gate, now))
    outcome2 = gate.handle(obs2, _ctx(gate, now + timedelta(seconds=1)))

    assert outcome2.decision.action.value == "drop"
    assert any(o.obs_type == ObservationType.ALERT for o in outcome2.emit)


def test_overload_bypass():
    gate = DefaultGate()
    obs = _make_message_obs("hello")
    ctx = _ctx(gate, datetime.now(timezone.utc), system_health={"overload": True})
    outcome = gate.handle(obs, ctx)

    assert outcome.decision.action.value == "drop"
    assert any(o.obs_type == ObservationType.ALERT for o in outcome.emit)
