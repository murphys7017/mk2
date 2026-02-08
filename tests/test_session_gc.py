import asyncio
import pytest

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

    task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.05)  # 等 core 启动

    # 注入一条消息，制造一个 session
    sk = "dm:test"
    core.bus.publish_nowait(
        Observation(obs_type=ObservationType.MESSAGE, session_key=sk, actor=Actor(actor_id="u2", actor_type="user"), payload=MessagePayload(text="2", extra={"i": 2}))
    )

    # 等待消息被处理 + 进入 idle
    await asyncio.sleep(0.35)  # > idle_ttl

    # 再等一个 sweep
    await asyncio.sleep(0.1)

    # 断言：session 被回收（字段名按你的实现调整）
    assert sk not in core._states
    assert sk not in core._workers

    # 断言：回收计数增长（如果你有）
    assert core.metrics.sessions_gc_total >= 1
    
    await core.shutdown()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

