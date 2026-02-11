from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List

import pytest

from src.gate.types import GateAction, GateDecision, GateOutcome, Scene
from src.schemas.observation import Observation, ObservationType, Actor, MessagePayload, AlertPayload


class FakeBus:
    def __init__(self) -> None:
        self.published: List[Observation] = []

    def publish_nowait(self, obs: Observation):
        self.published.append(obs)
        return type("Result", (), {"ok": True, "dropped": False, "reason": None})()


class FakeAgent:
    def __init__(self) -> None:
        self.called_with = []

    async def handle(self, obs: Observation, decision: GateDecision, ctx=None):
        self.called_with.append((obs, decision, ctx))


@dataclass
class FakeGate:
    outcome: GateOutcome
    ingested: List[Observation]

    def handle(self, obs, ctx):
        return self.outcome

    def ingest(self, obs, decision):
        self.ingested.append(obs)


class FakeWorker:
    def __init__(self, bus: FakeBus, gate: FakeGate, agent: FakeAgent) -> None:
        self._bus = bus
        self._gate = gate
        self._agent = agent

    async def step_once(self, obs: Observation):
        outcome = self._gate.handle(obs, ctx=None)

        for e in outcome.emit:
            self._bus.publish_nowait(e)

        for x in outcome.ingest:
            self._gate.ingest(x, outcome.decision)

        action = outcome.decision.action
        if action in (GateAction.DROP, GateAction.SINK):
            return

        await self._agent.handle(obs, outcome.decision, None)


def _make_obs(text: str = "hi") -> Observation:
    return Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="text_input",
        session_key="dm:test",
        actor=Actor(actor_id="u1", actor_type="user"),
        payload=MessagePayload(text=text),
    )


@pytest.mark.asyncio
async def test_drop_emits_alert_without_agent():
    obs = _make_obs()
    alert = Observation(
        obs_type=ObservationType.ALERT,
        source_name="gate",
        session_key="system",
        actor=Actor(actor_id="system", actor_type="system"),
        payload=AlertPayload(alert_type="gate_alert", severity="medium", message="alert"),
    )

    decision = GateDecision(
        action=GateAction.DROP,
        scene=Scene.DIALOGUE,
        session_key="dm:test",
        score=0.0,
    )
    outcome = GateOutcome(decision=decision, emit=[alert], ingest=[])

    bus = FakeBus()
    agent = FakeAgent()
    gate = FakeGate(outcome=outcome, ingested=[])

    worker = FakeWorker(bus, gate, agent)
    await worker.step_once(obs)

    assert len(bus.published) == 1
    assert len(agent.called_with) == 0


@pytest.mark.asyncio
async def test_sink_ingest_without_agent():
    obs = _make_obs()
    decision = GateDecision(
        action=GateAction.SINK,
        scene=Scene.DIALOGUE,
        session_key="dm:test",
        score=0.4,
    )
    outcome = GateOutcome(decision=decision, emit=[], ingest=[obs])

    bus = FakeBus()
    agent = FakeAgent()
    gate = FakeGate(outcome=outcome, ingested=[])

    worker = FakeWorker(bus, gate, agent)
    await worker.step_once(obs)

    assert len(gate.ingested) == 1
    assert len(agent.called_with) == 0


@pytest.mark.asyncio
async def test_deliver_calls_agent():
    obs = _make_obs("deliver")
    decision = GateDecision(
        action=GateAction.DELIVER,
        scene=Scene.DIALOGUE,
        session_key="dm:test",
        score=0.9,
        model_tier="high",
    )
    outcome = GateOutcome(decision=decision, emit=[], ingest=[])

    bus = FakeBus()
    agent = FakeAgent()
    gate = FakeGate(outcome=outcome, ingested=[])

    worker = FakeWorker(bus, gate, agent)
    await worker.step_once(obs)

    assert len(agent.called_with) == 1
    _, called_decision, _ = agent.called_with[0]
    assert called_decision.model_tier == "high"
