from __future__ import annotations

from datetime import datetime, timezone

from src.gate import DefaultGate, GateConfig, GateContext
from src.schemas.observation import Actor, MessagePayload, Observation, ObservationType


def test_deliver_session_override_does_not_apply_to_agent_messages():
    cfg = GateConfig()
    cfg.overrides.deliver_sessions = ["demo"]
    gate = DefaultGate(config=cfg)

    obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="agent:speaker",
        session_key="demo",
        actor=Actor(actor_id="agent", actor_type="system"),
        payload=MessagePayload(text="agent reply"),
    )
    ctx = GateContext(
        now=datetime.now(timezone.utc),
        config=gate.config,
        system_session_key="system",
        metrics=gate.metrics,
        session_state=None,
        system_health=None,
    )

    outcome = gate.handle(obs, ctx)
    assert outcome.decision.action.value == "sink"
