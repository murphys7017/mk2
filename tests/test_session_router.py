import asyncio
import pytest

from src.input_bus import AsyncInputBus
from src.schemas.observation import (
    Actor,
    MessagePayload,
    Observation,
    ObservationType,
    SchedulePayload,
)
from src.session_router import SessionRouter


pytestmark = pytest.mark.asyncio


async def _get_n(inbox, n: int, timeout: float = 1.0):
    """Helper: pull N items from inbox with timeout."""
    out = []
    for _ in range(n):
        item = await asyncio.wait_for(inbox.get(), timeout=timeout)
        out.append(item)
    return out


async def _run_router_for_test(router: SessionRouter):
    """Run router until bus ends."""
    await router.run()


async def _shutdown(bus: AsyncInputBus, task: asyncio.Task):
    """Close bus and await router task."""
    bus.close()
    await asyncio.wait_for(task, timeout=1.0)


async def _wait_until(predicate, *, timeout: float = 1.0, interval: float = 0.01):
    """Wait until predicate() is True or timeout; raise on timeout."""
    start = asyncio.get_event_loop().time()
    while True:
        if predicate():
            return
        if asyncio.get_event_loop().time() - start > timeout:
            raise TimeoutError("wait_until timeout")
        await asyncio.sleep(interval)


async def test_router_routes_and_preserves_order_print_observations():
    bus = AsyncInputBus(maxsize=64)
    router = SessionRouter(bus, inbox_maxsize=16)

    task = asyncio.create_task(_run_router_for_test(router))

    # Two sessions interleaved
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:A",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="1", extra={"i": 1}),
        )
    )
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:B",
            actor=Actor(actor_id="u2", actor_type="user"),
            payload=MessagePayload(text="x", extra={"i": "x"}),
        )
    )
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:A",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="2", extra={"i": 2}),
        )
    )
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:B",
            actor=Actor(actor_id="u2", actor_type="user"),
            payload=MessagePayload(text="y", extra={"i": "y"}),
        )
    )
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:A",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="3", extra={"i": 3}),
        )
    )
    inbox_a = router.get_inbox("s:A")
    inbox_b = router.get_inbox("s:B")

    got_a = await _get_n(inbox_a, 3)
    got_b = await _get_n(inbox_b, 2)

    # Print so you can visually inspect (run with pytest -s)
    print("\n[TEST] got_a:")
    for o in got_a:
        print(" ", o)
    print("[TEST] got_b:")
    for o in got_b:
        print(" ", o)

    assert [o.payload.extra["i"] for o in got_a] == [1, 2, 3]
    assert [o.payload.extra["i"] for o in got_b] == ["x", "y"]

    await _shutdown(bus, task)


async def test_router_resolves_missing_session_key():
    bus = AsyncInputBus(maxsize=64)
    # message_routing 默认是 "user"：MESSAGE 且无 session_key -> user:{actor}
    router = SessionRouter(bus, inbox_maxsize=16, message_routing="user", system_session_key="system")

    task = asyncio.create_task(_run_router_for_test(router))

    # MESSAGE missing session_key -> user:u1
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key=None,
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="hi", extra={"msg": "hi"}),
        )
    )

    # Non-MESSAGE missing session_key -> system
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.SCHEDULE,
            source_name="test",
            session_key=None,
            actor=Actor(actor_id="timer", actor_type="service"),
            payload=SchedulePayload(schedule_id="tick", data={"t": 1}),
        )
    )

    inbox_u1 = router.get_inbox("user:u1")
    inbox_sys = router.get_inbox("system")

    got_u1 = await _get_n(inbox_u1, 1)
    got_sys = await _get_n(inbox_sys, 1)

    print("\n[TEST] resolved user inbox obs:", got_u1[0])
    print("[TEST] resolved system inbox obs:", got_sys[0])

    assert got_u1[0].payload.extra["msg"] == "hi"
    assert got_sys[0].payload.data["t"] == 1

    await _shutdown(bus, task)


async def test_router_drops_when_inbox_full_drop_newest():
    bus = AsyncInputBus(maxsize=64)
    # inbox_maxsize=1 -> very easy to overflow
    router = SessionRouter(bus, inbox_maxsize=1)

    task = asyncio.create_task(_run_router_for_test(router))

    # Same session, 2 messages, inbox size=1 => drop newest (second)
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:full",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="1", extra={"i": 1}),
        )
    )
    bus.publish_nowait(
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test",
            session_key="s:full",
            actor=Actor(actor_id="u1", actor_type="user"),
            payload=MessagePayload(text="2", extra={"i": 2}),
        )
    )

    # Ensure router has consumed both items before asserting drop stats.
    await _wait_until(lambda: bus.consumed_total >= 2, timeout=1.0)

    inbox = router.get_inbox("s:full")

    got = await _get_n(inbox, 1)
    print("\n[TEST] inbox kept:", got[0])
    print("[TEST] inbox stats:", inbox.stats)
    print("[TEST] router dropped_total:", router.dropped_total)

    assert got[0].payload.extra["i"] == 1
    assert inbox.stats.dropped == 1
    assert router.dropped_total == 1

    await _shutdown(bus, task)
