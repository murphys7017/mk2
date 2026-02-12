import asyncio
import pytest

from src.agent.types import AgentOutcome
from src.schemas.observation import Actor, MessagePayload, Observation, ObservationType
from src.core import Core

pytestmark = pytest.mark.asyncio


async def test_session_gc_removes_idle_sessions():
    # 把 TTL/扫频调小，让测试秒级完成
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=16,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
        enable_session_gc=True,
        idle_ttl_seconds=0.2,
        gc_sweep_interval_seconds=0.05,
    )

    async def stub_handle(req):
        return AgentOutcome(emit=[], trace={}, error=None)

    core.agent_orchestrator.handle = stub_handle

    task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.05)  # 等 core 启动

    # 注入一条消息，制造一个 session
    sk = "dm:test"
    core.bus.publish_nowait(
        Observation(obs_type=ObservationType.MESSAGE, session_key=sk, actor=Actor(actor_id="u2", actor_type="user"), payload=MessagePayload(text="2", extra={"i": 2}))
    )

    # 等待消息被处理 + 进入 idle
    # idle_ttl_seconds=0.2, gc_sweep_interval_seconds=0.05
    # 需要：消息处理 + 进入 idle 状态 + GC 扫描
    # 保守估计：等待 1 秒确保发生
    await asyncio.sleep(1.0)

    # 断言：session 被回收（字段名按你的实现调整）
    assert sk not in core._states, f"Session {sk} should be GC'd but still in _states"
    assert sk not in core._workers, f"Session {sk} should be GC'd but still in _workers"

    # 断言：回收计数增长（如果你有）
    assert core.metrics.sessions_gc_total >= 1
    
    await core.shutdown()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_session_gc_recreates_worker_on_new_message():
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=16,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
        enable_session_gc=True,
        idle_ttl_seconds=0.2,
        gc_sweep_interval_seconds=0.05,
    )

    async def stub_handle(req):
        return AgentOutcome(emit=[], trace={}, error=None)

    core.agent_orchestrator.handle = stub_handle

    task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.05)

    sk = "dm:test"
    core.bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            session_key=sk,
            actor=Actor(actor_id="u2", actor_type="user"),
            payload=MessagePayload(text="first"),
        )
    )

    await asyncio.sleep(1.0)
    assert sk not in core._workers

    core.bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            session_key=sk,
            actor=Actor(actor_id="u2", actor_type="user"),
            payload=MessagePayload(text="second"),
        )
    )

    deadline = asyncio.get_event_loop().time() + 1.0
    while asyncio.get_event_loop().time() < deadline:
        if core.metrics.processed_by_session.get(sk, 0) >= 2:
            break
        await asyncio.sleep(0.05)

    assert core.metrics.processed_by_session.get(sk, 0) >= 2

    await core.shutdown()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

