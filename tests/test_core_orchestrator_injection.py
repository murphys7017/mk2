from __future__ import annotations

import asyncio

import pytest

from src.agent.types import AgentOutcome
from src.core import Core
from src.schemas.observation import Actor, MessagePayload, Observation, ObservationType


pytestmark = pytest.mark.asyncio


async def _wait_until(predicate, *, timeout: float = 2.0, interval: float = 0.02):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("wait_until timeout")


class SpyOrchestrator:
    def __init__(self) -> None:
        self.calls = 0

    async def handle(self, req):
        self.calls += 1
        return AgentOutcome(emit=[], trace={}, error=None)


async def test_core_accepts_injected_orchestrator():
    spy = SpyOrchestrator()
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=16,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
        enable_session_gc=False,
        agent_orchestrator=spy,
    )

    task = asyncio.create_task(core.run_forever())
    await _wait_until(lambda: core._router_task is not None and core._watcher_task is not None)

    core.bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test_input",
            session_key="dm:test",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="hello"),
        )
    )

    await _wait_until(lambda: spy.calls >= 1)
    assert spy.calls == 1

    await core.shutdown()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
