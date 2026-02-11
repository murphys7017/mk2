from __future__ import annotations

from datetime import datetime, timezone, timedelta
import time

import pytest

from src.config_provider import GateConfigProvider
from src.system_reflex.controller import SystemReflexController, make_control
from src.system_reflex.types import ReflexConfig
from src.schemas.observation import Observation, ObservationType, Actor, ControlPayload


def _make_suggestion(overrides: dict, ttl_sec: int = 2) -> Observation:
    payload = ControlPayload(
        kind="tuning_suggestion",
        data={
            "scope": "global",
            "suggested_overrides": overrides,
            "ttl_sec": ttl_sec,
            "reason": "latency_high",
            "ts": datetime.now(timezone.utc).timestamp(),
        },
    )
    return Observation(
        obs_type=ObservationType.CONTROL,
        source_name="agent",
        session_key="system",
        actor=Actor(actor_id="agent", actor_type="service"),
        payload=payload,
    )


def _make_provider(tmp_path) -> GateConfigProvider:
    path = tmp_path / "gate.yaml"
    path.write_text("version: 1\nscene_policies: {}\n", encoding="utf-8")
    return GateConfigProvider(path)


def test_suggestion_applied_force_low_model(tmp_path):
    provider = _make_provider(tmp_path)
    controller = SystemReflexController(provider, config=ReflexConfig())

    obs = _make_suggestion({"force_low_model": True}, ttl_sec=2)
    emits = controller.handle_observation(obs, datetime.now(timezone.utc))

    assert provider.snapshot().overrides.force_low_model is True
    kinds = [e.payload.kind for e in emits if hasattr(e.payload, "kind")]
    assert "tuning_applied" in kinds
    assert "system_mode_changed" in kinds


def test_whitelist_blocks_emergency_mode(tmp_path):
    provider = _make_provider(tmp_path)
    controller = SystemReflexController(provider, config=ReflexConfig())

    obs = _make_suggestion({"emergency_mode": True, "force_low_model": True}, ttl_sec=2)
    emits = controller.handle_observation(obs, datetime.now(timezone.utc))

    snap = provider.snapshot().overrides
    assert snap.emergency_mode is False
    assert snap.force_low_model is True

    applied = [e for e in emits if hasattr(e.payload, "kind") and e.payload.kind == "tuning_applied"][0]
    assert "emergency_mode" not in applied.payload.data.get("applied_overrides", {})


def test_ttl_expire_reverts(tmp_path):
    provider = _make_provider(tmp_path)
    controller = SystemReflexController(provider, config=ReflexConfig(suggestion_ttl_default_sec=1))

    obs = _make_suggestion({"force_low_model": True}, ttl_sec=1)
    controller.handle_observation(obs, datetime.now(timezone.utc))
    assert provider.snapshot().overrides.force_low_model is True

    # advance time
    future = datetime.now(timezone.utc) + timedelta(seconds=2)
    emits = controller.handle_observation(obs, future)

    assert provider.snapshot().overrides.force_low_model is False
    kinds = [e.payload.kind for e in emits if hasattr(e.payload, "kind")]
    assert "tuning_applied" in kinds
    assert "system_mode_changed" in kinds


def test_suggestion_cooldown(tmp_path):
    provider = _make_provider(tmp_path)
    controller = SystemReflexController(
        provider, config=ReflexConfig(suggestion_cooldown_sec=10)
    )

    obs = _make_suggestion({"force_low_model": True}, ttl_sec=2)
    emits1 = controller.handle_observation(obs, datetime.now(timezone.utc))
    assert provider.snapshot().overrides.force_low_model is True

    # second suggestion within cooldown
    emits2 = controller.handle_observation(obs, datetime.now(timezone.utc))

    applied2 = [e for e in emits2 if hasattr(e.payload, "kind") and e.payload.kind == "tuning_applied"][0]
    assert applied2.payload.data.get("accepted") is False
