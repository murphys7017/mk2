from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from src.agent.answerer import LLMAnswerer
from src.agent.types import AgentRequest, AnswerSpec, EvidencePack
from src.gate.types import GateAction, GateDecision, Scene
from src.schemas.observation import Actor, MessagePayload, Observation, ObservationType
from src.session_router import SessionState


class SlowGateway:
    def call(self, messages, **params):
        time.sleep(0.2)
        return "ok"


@pytest.mark.asyncio
async def test_llm_answerer_does_not_block_event_loop():
    answerer = object.__new__(LLMAnswerer)
    answerer._gateway = SlowGateway()

    req = AgentRequest(
        obs=Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="dm:test",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="hi"),
        ),
        gate_decision=GateDecision(
            action=GateAction.DELIVER,
            scene=Scene.DIALOGUE,
            session_key="dm:test",
        ),
        session_state=SessionState("dm:test"),
        now=datetime.now(timezone.utc),
    )

    ticks = {"count": 0}
    stop = {"done": False}

    async def ticker():
        while not stop["done"]:
            ticks["count"] += 1
            await asyncio.sleep(0.01)

    tick_task = asyncio.create_task(ticker())
    try:
        await answerer.answer(req, EvidencePack(items=[]), AnswerSpec())
    finally:
        stop["done"] = True
        await tick_task

    assert ticks["count"] >= 5
