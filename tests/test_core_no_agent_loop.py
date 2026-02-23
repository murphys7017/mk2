from __future__ import annotations

import asyncio

import pytest

from src.agent.types import AgentOutcome
from src.core import Core
from src.schemas.observation import (
    Actor,
    MessagePayload,
    Observation,
    ObservationType,
    SourceKind,
)


pytestmark = pytest.mark.asyncio


async def _wait_until(predicate, *, timeout: float = 2.0, interval: float = 0.02):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("wait_until timeout")


async def test_agent_emit_does_not_retrigger_agent():
    core = Core(
        bus_maxsize=200,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
        enable_session_gc=False,
    )

    calls = {"count": 0}

    async def stub_handle(req):
        calls["count"] += 1
        emit = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="agent:speaker",
            source_kind=SourceKind.INTERNAL,
            session_key=req.obs.session_key,
            actor=Actor(actor_id="agent", actor_type="system"),
            payload=MessagePayload(text="stub reply"),
        )
        return AgentOutcome(emit=[emit], trace={}, error=None)

    core.agent_queen.handle = stub_handle

    task = asyncio.create_task(core.run_forever())
    await _wait_until(lambda: core._router_task is not None and core._watcher_task is not None)

    core.bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test_input",
            source_kind=SourceKind.EXTERNAL,
            session_key="demo",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="hello"),
        )
    )

    await _wait_until(lambda: core.get_state("demo").processed_total >= 2)
    observed_calls = calls["count"]
    await _wait_until(lambda: calls["count"] == observed_calls, timeout=0.3, interval=0.05)
    assert calls["count"] == 1

    await core.shutdown()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
