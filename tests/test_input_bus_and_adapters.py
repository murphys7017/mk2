# tests/test_input_bus_and_adapters.py

import pytest
from typing import cast

from src.input_bus import AsyncInputBus
from src.schemas.observation import ObservationType

from src.adapters.timer_tick_adapter import TimerTickAdapter
from src.adapters.text_input_adapter import TextInputAdapter


@pytest.mark.asyncio
async def test_text_input_adapter_emits_message():
    bus = AsyncInputBus(maxsize=10, drop_when_full=True)

    adapter = TextInputAdapter()
    adapter.start(bus)

    adapter.ingest_text("hello", actor_id="u1", session_key="dm:u1")

    obs = await bus.get(timeout=0.5)
    assert obs is not None
    assert obs.obs_type == ObservationType.MESSAGE
    assert obs.session_key == "dm:u1"
    assert obs.actor.actor_id == "u1"
    assert getattr(obs.payload, "text", None) == "hello"

    bus.close()


@pytest.mark.asyncio
async def test_timer_tick_adapter_emits_schedule():
    bus = AsyncInputBus(maxsize=10, drop_when_full=True)

    adapter = TimerTickAdapter(schedule_id="tick_test", session_key="system:timer_test")
    adapter.start(bus)

    adapter.trigger(reason="unit_test")

    obs = await bus.get(timeout=0.5)
    assert obs is not None
    assert obs.obs_type == ObservationType.SCHEDULE
    assert obs.session_key == "system:timer_test"
    assert getattr(obs.payload, "schedule_id", None) == "tick_test"

    bus.close()


class BoomTimer(TimerTickAdapter):
    """故意崩溃，用来验证错误会变成 ALERT"""
    def observe_once(self):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_active_adapter_error_turns_into_alert():
    bus = AsyncInputBus(maxsize=10, drop_when_full=True)

    adapter = BoomTimer(name="boom_timer")
    adapter.start(bus)

    adapter.trigger(reason="boom_test")

    obs = await bus.get(timeout=0.5)
    assert obs is not None
    assert obs.obs_type == ObservationType.ALERT
    assert getattr(obs.payload, "alert_type", None) == "adapter_observe_error"

    bus.close()
