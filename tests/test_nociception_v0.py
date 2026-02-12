import asyncio
import pytest

from src.core import Core
from src.schemas.observation import Actor, AlertPayload, Observation, ObservationType
from src.nociception import make_pain_alert, extract_pain_key

pytestmark = pytest.mark.asyncio


async def _stop_core(run_task: asyncio.Task, core, timeout: float = 1.5):
    """
    Gracefully stop Core with timeout protection.

    - First attempt core.shutdown() if available.
    - Then cancel run_task.
    - Await with timeout to prevent hanging teardown.
    """
    try:
        if hasattr(core, "shutdown"):
            await core.shutdown()
    except Exception:
        pass

    run_task.cancel()

    try:
        await asyncio.wait_for(
            asyncio.gather(run_task, return_exceptions=True),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        # Fail fast instead of hanging forever
        raise RuntimeError("Core shutdown timeout in test teardown")


async def test_pain_aggregation():
    """Test 1: pain 聚合"""
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
    )

    run_task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.1)

    try:
        # 投递 3 条同源 ALERT（adapter:a1）
        for i in range(3):
            pain = make_pain_alert(
                source_kind="adapter",
                source_id="a1",
                severity="medium",
                message=f"Error {i}",
                session_key="system",
            )
            core.bus.publish_nowait(pain)

        # 等待处理（用 polling 代替固定 sleep）
        max_wait = 2.0
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < max_wait:
            if core.metrics.pain_total >= 3:
                break
            await asyncio.sleep(0.05)

        # 断言
        assert core.metrics.pain_total == 3, f"Expected 3, got {core.metrics.pain_total}"
        assert core.metrics.pain_by_source["adapter:a1"] == 3
        print("✅ Test 1 passed: pain aggregation")

    finally:
        await _stop_core(run_task, core)


async def test_burst_triggers_cooldown():
    """Test 2: burst 触发 cooldown"""
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
    )

    run_task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.1)

    try:
        # 短时间投递 5 条同源 pain（达到 BURST_THRESHOLD）
        for i in range(5):
            pain = make_pain_alert(
                source_kind="adapter",
                source_id="a2",
                severity="high",
                message=f"Burst {i}",
                session_key="system",
            )
            core.bus.publish_nowait(pain)
            await asyncio.sleep(0.01)  # 快速连续

        # 等待处理和触发检测（用 polling）
        max_wait = 2.0
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < max_wait:
            if "a2" in core.adapters_disabled_until or core.metrics.adapters_cooldown_total >= 1:
                break
            await asyncio.sleep(0.05)

        # 断言 cooldown 被设置
        assert "a2" in core.adapters_disabled_until
        assert core.metrics.adapters_cooldown_total >= 1
        print("✅ Test 2 passed: burst triggers cooldown")

    finally:
        await _stop_core(run_task, core)


async def test_drop_overload_suppresses_fanout():
    """Test 3: drop overload 触发 fanout suppression"""
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=True,
        enable_session_gc=False,
    )

    run_task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.1)

    try:
        # 模拟 drop overload（mock dropped_total）
        # 这里简单演示：直接调用 _on_system_tick 来测试逻辑
        import time
        core.drops_last = 0

        # 模拟 bus 有大量 drops（直接设置，不走实际 drop）
        if not hasattr(core.bus, "dropped_total"):
            core.bus.dropped_total = 0

        # 注入一条 SCHEDULE observation
        from src.schemas.observation import SourceKind, SchedulePayload

        tick_obs = Observation(
            obs_type=ObservationType.SCHEDULE,
            source_name="timer",
            source_kind=SourceKind.INTERNAL,
            session_key="system",
            actor=Actor(actor_id="system", actor_type="system"),
            payload=SchedulePayload(schedule_id="heartbeat"),
        )

        # 模拟 drop（在处理 tick 前设置）
        core.bus.dropped_total = 100  # >= DROP_BURST_THRESHOLD (50)

        # 处理 tick
        await core._on_system_tick(tick_obs)

        # 等待处理（用 polling）
        max_wait = 1.0
        start_time = asyncio.get_event_loop().time()
        import time
        while asyncio.get_event_loop().time() - start_time < max_wait:
            if core.metrics.drops_overload_total >= 1 or core.fanout_disabled_until > time.time() - 1:
                break
            await asyncio.sleep(0.05)

        # 断言
        assert core.metrics.drops_overload_total >= 1
        assert core.fanout_disabled_until > time.time() - 1  # 最近被设置过
        print("✅ Test 3 passed: drop overload suppresses fanout")

    finally:
        await _stop_core(run_task, core)


async def test_extract_pain_key():
    """Test 4: extract_pain_key 正确解析"""
    pain = make_pain_alert(
        source_kind="adapter",
        source_id="text_input",
        severity="low",
        message="test",
    )

    key = extract_pain_key(pain)
    assert key == "adapter:text_input"
    print("✅ Test 4 passed: extract_pain_key")


if __name__ == "__main__":
    asyncio.run(test_pain_aggregation())
    asyncio.run(test_burst_triggers_cooldown())
    asyncio.run(test_drop_overload_suppresses_fanout())
    asyncio.run(test_extract_pain_key())
    print("\n✅ All nociception tests passed!")
