from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .types import ReflexConfig, SuggestionState
from ..config_provider import GateConfigProvider
from ..schemas.observation import (
    Observation,
    ObservationType,
    Actor,
    AlertPayload,
    ControlPayload,
    SourceKind,
)


def is_alert(obs: Observation) -> bool:
    return obs.obs_type == ObservationType.ALERT


def is_control(obs: Observation) -> bool:
    return obs.obs_type == ObservationType.CONTROL


def get_payload(obs: Observation) -> Dict[str, Any]:
    payload = obs.payload
    if isinstance(payload, ControlPayload):
        data = dict(payload.data)
        data["kind"] = payload.kind
        return data
    if isinstance(payload, AlertPayload):
        data = dict(payload.data)
        data["alert_type"] = payload.alert_type
        return data
    if isinstance(payload, dict):
        return payload
    return {}


def control_kind(obs: Observation) -> Optional[str]:
    if not is_control(obs):
        return None
    payload = get_payload(obs)
    return payload.get("kind")


def alert_kind(obs: Observation) -> Optional[str]:
    if not is_alert(obs):
        return None
    payload = get_payload(obs)
    return payload.get("alert_type")


def extract_ts(payload: Dict[str, Any], now: datetime) -> float:
    ts = payload.get("ts")
    if isinstance(ts, (int, float)):
        return float(ts)
    return now.timestamp()


def make_control(session_key: str, payload: Dict[str, Any], actor: str = "system") -> Observation:
    kind = payload.get("kind", "unknown")
    data = dict(payload)
    data.pop("kind", None)
    return Observation(
        obs_type=ObservationType.CONTROL,
        source_name="system_reflex",
        source_kind=SourceKind.INTERNAL,
        session_key=session_key,
        actor=Actor(actor_id=actor, actor_type="system"),
        payload=ControlPayload(kind=kind, data=data),
    )


def make_alert(session_key: str, payload: Dict[str, Any], actor: str = "system") -> Observation:
    alert_type = payload.get("alert_type", "system_reflex_warning")
    data = dict(payload)
    data.pop("alert_type", None)
    return Observation(
        obs_type=ObservationType.ALERT,
        source_name="system_reflex",
        source_kind=SourceKind.INTERNAL,
        session_key=session_key,
        actor=Actor(actor_id=actor, actor_type="system"),
        payload=AlertPayload(alert_type=alert_type, severity="medium", message=payload.get("message"), data=data),
    )


class SystemReflexController:
    def __init__(
        self,
        config_provider: GateConfigProvider,
        *,
        config: Optional[ReflexConfig] = None,
        system_session_key: str = "system",
    ) -> None:
        self.config_provider = config_provider
        self.config = config or ReflexConfig()
        self.system_session_key = system_session_key
        self.suggestion_state = SuggestionState()

    def handle_observation(self, obs: Observation, now: datetime) -> List[Observation]:
        emits: List[Observation] = []
        try:
            if is_control(obs) and control_kind(obs) == "tuning_suggestion":
                emits.extend(self.handle_tuning_suggestion(obs, now))

            emits.extend(self._evaluate_suggestion_ttl(now))
        except Exception as e:
            emits.append(
                make_alert(
                    self.system_session_key,
                    {
                        "alert_type": "system_reflex_error",
                        "message": str(e),
                    },
                )
            )
        return emits

    def handle_tuning_suggestion(self, obs: Observation, now: datetime) -> List[Observation]:
        emits: List[Observation] = []
        payload = get_payload(obs)
        now_ts = extract_ts(payload, now)

        if not self.config.allow_agent_suggestions:
            emits.append(self._emit_tuning_applied(False, {}, "agent_suggestion_disabled", now_ts))
            return emits

        suggested = payload.get("suggested_overrides", {}) or {}
        allowed: Dict[str, Any] = {
            k: v for k, v in suggested.items() if k in self.config.agent_override_whitelist
        }

        if not allowed:
            emits.append(self._emit_tuning_applied(False, {}, "no_allowed_overrides", now_ts))
            return emits

        ttl = payload.get("ttl_sec", self.config.suggestion_ttl_default_sec)
        if not isinstance(ttl, (int, float)):
            ttl = self.config.suggestion_ttl_default_sec
        ttl = max(1, min(int(ttl), 3600))

        last_ts = self.suggestion_state.last_applied_ts
        if last_ts is not None and (now_ts - last_ts) < self.config.suggestion_cooldown_sec:
            emits.append(self._emit_tuning_applied(False, {}, "cooldown", now_ts))
            return emits

        changed = self.config_provider.update_overrides(**allowed)
        if changed:
            self.suggestion_state.active_until_ts = now_ts + ttl
            self.suggestion_state.last_applied_ts = now_ts
            self.suggestion_state.active_overrides = dict(allowed)

        emits.append(self._emit_tuning_applied(changed, allowed if changed else {}, "agent_suggestion", now_ts))
        if changed:
            emits.append(self._emit_system_mode_changed("agent_suggestion", now_ts))
        return emits

    def _evaluate_suggestion_ttl(self, now: datetime) -> List[Observation]:
        emits: List[Observation] = []
        if self.suggestion_state.active_until_ts is None:
            return emits

        now_ts = now.timestamp()
        if now_ts <= self.suggestion_state.active_until_ts:
            return emits

        # TTL expired, revert overrides
        revert: Dict[str, Any] = {}
        for k in self.suggestion_state.active_overrides.keys():
            if k == "force_low_model":
                revert[k] = False

        changed = self.config_provider.update_overrides(**revert)
        self.suggestion_state.active_until_ts = None
        self.suggestion_state.active_overrides = {}

        emits.append(self._emit_tuning_applied(changed, revert if changed else {}, "ttl_expired", now_ts))
        if changed:
            emits.append(self._emit_system_mode_changed("ttl_expired", now_ts))
        return emits

    def _emit_tuning_applied(self, accepted: bool, applied_overrides: Dict[str, Any], reason: str, ts: float) -> Observation:
        payload = {
            "kind": "tuning_applied",
            "scope": "global",
            "applied_overrides": applied_overrides,
            "accepted": accepted,
            "reason": reason,
            "ts": ts,
        }
        return make_control(self.system_session_key, payload)

    def _emit_system_mode_changed(self, reason: str, ts: float) -> Observation:
        overrides = self.config_provider.snapshot().overrides
        payload = {
            "kind": "system_mode_changed",
            "scope": "global",
            "mode": {
                "emergency_mode": overrides.emergency_mode,
                "force_low_model": overrides.force_low_model,
            },
            "reason": reason,
            "ts": ts,
        }
        return make_control(self.system_session_key, payload)
