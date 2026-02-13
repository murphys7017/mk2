from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from loguru import logger
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Allow running this script directly from repository root:
# `python tools/demo_e2e.py ...`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.adapters.cli_adapter import CliInputAdapter
from src.adapters.timer_tick_adapter import TimerTickAdapter
from src.agent import DefaultAgentOrchestrator
from src.agent.answerer import StubAnswerer
from src.core import Core
from src.logging_config import setup_logging
from src.schemas.observation import (
    Actor,
    AlertPayload,
    ControlPayload,
    EvidenceRef,
    MessagePayload,
    Observation,
    ObservationType,
    SchedulePayload,
)


TRACE_EXTRA_KEY = "e2e_trace"


def _enum_to_str(v: Any) -> Any:
    return getattr(v, "value", v)


def _safe_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _trace(tag: str, data: dict[str, Any]) -> None:
    payload = {
        "tag": tag,
        "ts": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    logger.bind(**{TRACE_EXTRA_KEY: True}).info(_safe_json(payload))


def _payload_preview(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {"kind": "none"}
    if isinstance(payload, MessagePayload):
        return {"kind": "message", "text": payload.text}
    if isinstance(payload, AlertPayload):
        return {
            "kind": "alert",
            "alert_type": payload.alert_type,
            "severity": payload.severity,
            "message": payload.message,
            "data": payload.data,
        }
    if isinstance(payload, ControlPayload):
        return {"kind": "control", "control_kind": payload.kind, "data": payload.data}
    if isinstance(payload, SchedulePayload):
        return {"kind": "schedule", "schedule_id": payload.schedule_id, "data": payload.data}
    if isinstance(payload, dict):
        return {"kind": "dict", "keys": list(payload.keys())[:8], "size": len(payload)}
    if is_dataclass(payload):
        return {"kind": type(payload).__name__, "data": asdict(payload)}
    return {"kind": type(payload).__name__, "repr": str(payload)[:160]}


def _obs_preview(obs: Observation) -> dict[str, Any]:
    return {
        "obs_id": obs.obs_id,
        "obs_type": _enum_to_str(obs.obs_type),
        "source_name": obs.source_name,
        "source_kind": _enum_to_str(obs.source_kind),
        "session_key": obs.session_key,
        "actor_id": obs.actor.actor_id if obs.actor else None,
        "actor_type": obs.actor.actor_type if obs.actor else None,
        "payload": _payload_preview(obs.payload),
    }


class TracedTimerTickAdapter(TimerTickAdapter):
    def observe_once(self) -> Optional[Observation]:
        obs = super().observe_once()
        if obs is not None:
            _trace("ADAPTER:TIMER:OUT", _obs_preview(obs))
        return obs


class SafeCliInputAdapter(CliInputAdapter):
    """
    A CLI adapter variant that avoids run_in_executor(input).
    It reads stdin from a daemon thread and consumes lines in an async task.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._line_queue: asyncio.Queue[str] = asyncio.Queue()
        self._line_consumer_task: Optional[asyncio.Task] = None
        self._stdin_thread: Optional[threading.Thread] = None
        self._stdin_stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_start(self) -> None:
        logger.info("\n" + "=" * 60)
        logger.info("E2E Demo CLI started (safe mode)")
        logger.info("=" * 60)
        logger.info("Commands:")
        logger.info("  <text>                              - send text to current session")
        logger.info("  /session <key>                      - switch session_key")
        logger.info("  /tick                               - inject system tick")
        logger.info("  /alert <kind>                       - inject ALERT")
        logger.info("  /suggest force_low_model=0|1 ttl=<sec> - inject tuning_suggestion")
        logger.info("  /trace on|off                       - toggle gate trace (if implemented)")
        logger.info("  /quit                               - stop demo")
        logger.info("=" * 60 + "\n")

        self._stdin_stop.clear()
        self._loop = asyncio.get_running_loop()
        self._stdin_thread = threading.Thread(
            target=self._stdin_reader_loop,
            name=f"{self.name}_stdin_reader",
            daemon=True,
        )
        self._stdin_thread.start()
        self._line_consumer_task = asyncio.create_task(
            self._consume_lines_loop(),
            name=f"{self.name}_line_consumer",
        )

    def _on_stop(self) -> None:
        self._stdin_stop.set()
        if self._line_consumer_task and not self._line_consumer_task.done():
            self._line_consumer_task.cancel()

    def _stdin_reader_loop(self) -> None:
        while not self._stdin_stop.is_set():
            try:
                line = input(f"[session: {self.current_session_key}] > ")
            except EOFError:
                line = "/quit"
            except Exception as e:
                _trace("ADAPTER:CLI:ERROR", {"error": str(e)})
                break

            self._enqueue_line_from_thread(line)
            if line.strip().startswith("/quit"):
                break

    def _enqueue_line_from_thread(self, line: str) -> None:
        if self._loop is None or self._loop.is_closed():
            return

        def _put() -> None:
            if self._running:
                self._line_queue.put_nowait(line)

        try:
            self._loop.call_soon_threadsafe(_put)
        except RuntimeError:
            return

    async def _consume_lines_loop(self) -> None:
        while self._running:
            try:
                line = await self._line_queue.get()
                if not line.strip():
                    continue
                await self._process_command(line)
                if line.strip().startswith("/quit"):
                    break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _trace("ADAPTER:CLI:ERROR", {"error": str(e)})

    async def _inject_observation(
        self,
        obs_type: ObservationType,
        session_key: str,
        payload,
    ) -> None:
        if not self._running or self._bus is None:
            return

        try:
            now = datetime.now(timezone.utc)
            raw_event_id = f"cli:{self.current_session_key}:{int(now.timestamp() * 1000)}"
            obs = Observation(
                obs_type=obs_type,
                source_name=self.name,
                source_kind=self.source_kind,
                timestamp=now,
                received_at=now,
                session_key=session_key,
                actor=Actor(
                    actor_id="cli",
                    actor_type="user",
                    display_name="CLI User",
                ),
                payload=payload,
                evidence=EvidenceRef(
                    raw_event_id=raw_event_id,
                    raw_event_uri=f"cli://local/{session_key}",
                    extra={"source": "cli_adapter"},
                ),
                metadata={
                    "adapter": self.name,
                    "interaction_type": "manual",
                },
            )
            obs.validate()

            _trace("ADAPTER:CLI:OUT", _obs_preview(obs))
            result = self._bus.publish_nowait(obs)
            _trace(
                "ADAPTER:CLI:PUBLISH",
                {
                    "obs_id": obs.obs_id,
                    "ok": result.ok,
                    "dropped": result.dropped,
                    "reason": result.reason,
                },
            )
        except Exception as e:
            _trace("ADAPTER:CLI:ERROR", {"error": str(e)})


def _install_bus_trace(core: Core) -> None:
    bus = core.bus
    original_publish = bus.publish_nowait
    original_get = bus.get

    def traced_publish(obs: Observation):
        _trace("BUS:IN", _obs_preview(obs))
        result = original_publish(obs)
        _trace(
            "BUS:OUT",
            {
                "ok": result.ok,
                "dropped": result.dropped,
                "reason": result.reason,
                "queue_size": bus.size(),
                "published_total": bus.published_total,
                "consumed_total": bus.consumed_total,
                "dropped_total": bus.dropped_total,
            },
        )
        return result

    async def traced_get(timeout: Optional[float] = None):
        obs = await original_get(timeout)
        if obs is not None:
            _trace("BUS:DEQUEUE", _obs_preview(obs))
        return obs

    bus.publish_nowait = traced_publish  # type: ignore[assignment]
    bus.get = traced_get  # type: ignore[assignment]


def _install_router_trace(core: Core) -> None:
    router = core.router
    original_resolve = router.resolve_session_key
    original_get_inbox = router.get_inbox
    original_run = router.run

    def traced_resolve(obs: Observation) -> str:
        resolved = original_resolve(obs)
        _trace(
            "ROUTER:RESOLVE",
            {
                "obs_id": obs.obs_id,
                "obs_session_key": obs.session_key,
                "resolved_session_key": resolved,
                "active_sessions": router.list_active_sessions(),
            },
        )
        return resolved

    def traced_get_inbox(session_key: str):
        inbox = original_get_inbox(session_key)
        if not getattr(inbox, "_trace_wrapped", False):
            original_put = inbox.put_nowait
            original_get = inbox.get

            def traced_put(obs: Observation) -> bool:
                before = inbox.qsize()
                ok = original_put(obs)
                after = inbox.qsize()
                _trace(
                    "ROUTER:ENQUEUE",
                    {
                        "session_key": session_key,
                        "ok": ok,
                        "queue_before": before,
                        "queue_after": after,
                        "inbox_enqueued": inbox.stats.enqueued,
                        "inbox_dropped": inbox.stats.dropped,
                        "router_dropped_total": router.dropped_total,
                        "obs_id": obs.obs_id,
                        "obs_type": _enum_to_str(obs.obs_type),
                    },
                )
                return ok

            async def traced_get():
                obs = await original_get()
                _trace(
                    "WORKER:IN",
                    {
                        "session_key": session_key,
                        "obs": _obs_preview(obs),
                    },
                )
                return obs

            inbox.put_nowait = traced_put  # type: ignore[assignment]
            inbox.get = traced_get  # type: ignore[assignment]
            setattr(inbox, "_trace_wrapped", True)
        return inbox

    async def traced_run() -> None:
        _trace("ROUTER:RUN", {"event": "start"})
        try:
            await original_run()
        finally:
            _trace("ROUTER:RUN", {"event": "stop", "dropped_total": router.dropped_total})

    router.resolve_session_key = traced_resolve  # type: ignore[assignment]
    router.get_inbox = traced_get_inbox  # type: ignore[assignment]
    router.run = traced_run  # type: ignore[assignment]


def _install_core_trace(core: Core) -> None:
    original_handle = core._handle_observation

    async def traced_handle(session_key: str, obs: Observation, state, decision=None) -> None:
        _trace(
            "CORE:IN",
            {
                "session_key": session_key,
                "decision_action": _enum_to_str(getattr(decision, "action", None)),
                "state_processed_before": state.processed_total,
                "state_error_before": state.error_total,
                "obs": _obs_preview(obs),
            },
        )
        await original_handle(session_key, obs, state, decision)
        _trace(
            "CORE:OUT",
            {
                "session_key": session_key,
                "state_processed_after": state.processed_total,
                "state_error_after": state.error_total,
            },
        )

    core._handle_observation = traced_handle  # type: ignore[assignment]


def _install_gate_trace(core: Core) -> None:
    gate = core.gate
    original_handle = gate.handle

    def traced_handle(obs, ctx):
        _trace(
            "GATE:IN",
            {
                "obs_id": obs.obs_id,
                "session_key": obs.session_key,
                "obs_type": _enum_to_str(obs.obs_type),
                "state_processed": getattr(ctx.session_state, "processed_total", None),
            },
        )
        outcome = original_handle(obs, ctx)
        hint = outcome.decision.hint
        _trace(
            "GATE:OUT",
            {
                "obs_id": obs.obs_id,
                "action": _enum_to_str(outcome.decision.action),
                "scene": _enum_to_str(outcome.decision.scene),
                "score": outcome.decision.score,
                "model_tier": hint.model_tier if hint else None,
                "response_policy": hint.response_policy if hint else None,
                "emit_count": len(outcome.emit),
                "ingest_count": len(outcome.ingest),
            },
        )
        return outcome

    gate.handle = traced_handle  # type: ignore[assignment]


def _install_agent_trace(core: Core) -> None:
    orchestrator = core.agent_orchestrator
    original_handle = orchestrator.handle

    async def traced_handle(req):
        _trace(
            "AGENT:IN",
            {
                "session_key": req.obs.session_key,
                "gate_action": _enum_to_str(req.gate_decision.action),
                "obs": _obs_preview(req.obs),
                "state_processed": req.session_state.processed_total,
                "state_error": req.session_state.error_total,
            },
        )
        outcome = await original_handle(req)
        _trace(
            "AGENT:OUT",
            {
                "emit_count": len(outcome.emit),
                "error": outcome.error,
                "trace_elapsed_ms": outcome.trace.get("elapsed_ms") if outcome.trace else None,
                "trace_keys": sorted(list(outcome.trace.keys())) if outcome.trace else [],
            },
        )
        for emit_obs in outcome.emit:
            _trace("AGENT:EMIT", _obs_preview(emit_obs))
        return outcome

    orchestrator.handle = traced_handle  # type: ignore[assignment]


async def _wait_adapter_started(adapter, timeout_seconds: float = 5.0) -> None:
    start = asyncio.get_running_loop().time()
    while not adapter.running:
        if asyncio.get_running_loop().time() - start > timeout_seconds:
            raise TimeoutError(f"adapter '{adapter.name}' did not start in time")
        await asyncio.sleep(0.05)


async def _heartbeat_loop(
    timer_adapter: TracedTimerTickAdapter,
    stop_event: asyncio.Event,
    interval_seconds: float,
) -> None:
    _trace(
        "HEARTBEAT:LOOP",
        {
            "event": "start",
            "adapter": timer_adapter.name,
            "interval_seconds": interval_seconds,
        },
    )
    try:
        while not stop_event.is_set():
            if timer_adapter.running:
                timer_adapter.trigger(reason="heartbeat", context={"interval_seconds": interval_seconds})
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        raise
    finally:
        _trace("HEARTBEAT:LOOP", {"event": "stop", "adapter": timer_adapter.name})


def _build_orchestrator(args: argparse.Namespace) -> DefaultAgentOrchestrator:
    if args.agent_mode == "stub":
        return DefaultAgentOrchestrator(answerer=StubAnswerer())

    return DefaultAgentOrchestrator(
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        llm_config_path=args.llm_config,
    )


def _setup_logging(level_name: str) -> None:
    setup_logging(
        level=level_name.upper(),
        force=True,
        trace_key=TRACE_EXTRA_KEY,
        trace_only=True,
    )


async def _run_demo(args: argparse.Namespace) -> None:
    _setup_logging(args.log_level)

    stop_event = asyncio.Event()
    orchestrator = _build_orchestrator(args)
    core = Core(
        bus_maxsize=args.bus_maxsize,
        inbox_maxsize=args.inbox_maxsize,
        system_session_key=args.system_session_key,
        default_session_key=args.default_session_key,
        message_routing=args.message_routing,
        enable_system_fanout=args.enable_system_fanout,
        enable_session_gc=args.enable_session_gc,
        agent_orchestrator=orchestrator,
    )

    cli_adapter = SafeCliInputAdapter(name=args.cli_adapter_name)
    cli_adapter.set_stop_event(stop_event)
    # timer_adapter = TracedTimerTickAdapter(
    #     name=args.timer_adapter_name,
    #     schedule_id=args.heartbeat_schedule_id,
    #     session_key=args.system_session_key,
    # )

    core.add_adapter(cli_adapter)
    # core.add_adapter(timer_adapter)

    _install_bus_trace(core)
    _install_router_trace(core)
    _install_core_trace(core)
    _install_gate_trace(core)
    _install_agent_trace(core)

    _trace(
        "DEMO:START",
        {
            "agent_mode": args.agent_mode,
            "heartbeat_interval_seconds": args.heartbeat_interval,
            "system_session_key": args.system_session_key,
            "message_routing": args.message_routing,
            "enable_system_fanout": args.enable_system_fanout,
            "enable_session_gc": args.enable_session_gc,
        },
    )

    core_task = asyncio.create_task(core.run_forever(), name="core.run_forever")
    heartbeat_task: Optional[asyncio.Task] = None
    stop_wait_task: Optional[asyncio.Task] = None

    try:
        #await _wait_adapter_started(timer_adapter)
        # heartbeat_task = asyncio.create_task(
        #     _heartbeat_loop(timer_adapter, stop_event, args.heartbeat_interval),
        #     name="heartbeat_loop",
        # )
        stop_wait_task = asyncio.create_task(stop_event.wait(), name="stop_event.wait")

        done, _ = await asyncio.wait(
            {core_task, stop_wait_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if core_task in done:
            exc = core_task.exception()
            if exc is not None:
                raise exc
    finally:
        stop_event.set()

        if heartbeat_task is not None and not heartbeat_task.done():
            heartbeat_task.cancel()
        if stop_wait_task is not None and not stop_wait_task.done():
            stop_wait_task.cancel()

        await core.shutdown()
        if not core_task.done():
            core_task.cancel()

        await asyncio.gather(core_task, return_exceptions=True)
        if heartbeat_task is not None:
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        if stop_wait_task is not None:
            await asyncio.gather(stop_wait_task, return_exceptions=True)

    _trace("DEMO:STOP", {"active_sessions": core.active_sessions, "worker_stats": core.get_worker_stats()})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "E2E development tool: run CLI + timer adapters and trace adapter/bus/router/core/worker/agent I/O."
        )
    )
    parser.add_argument("--heartbeat-interval", type=float, default=2.0, help="Timer heartbeat interval in seconds.")
    parser.add_argument("--heartbeat-schedule-id", default="heartbeat", help="Schedule id used by timer adapter.")
    parser.add_argument("--cli-adapter-name", default="cli_adapter")
    parser.add_argument("--timer-adapter-name", default="timer_heartbeat")
    parser.add_argument("--bus-maxsize", type=int, default=1000)
    parser.add_argument("--inbox-maxsize", type=int, default=256)
    parser.add_argument("--system-session-key", default="system")
    parser.add_argument("--default-session-key", default="default")
    parser.add_argument("--message-routing", choices=["user", "default"], default="user")
    parser.add_argument("--enable-system-fanout", action="store_true")
    parser.add_argument("--enable-session-gc", action="store_true")
    parser.add_argument("--agent-mode", choices=["stub", "llm"], default="stub")
    parser.add_argument("--llm-provider", default="bailian")
    parser.add_argument("--llm-model", default="qwen-max")
    parser.add_argument("--llm-config", default="config/llm.yaml")
    parser.add_argument("--log-level", default="INFO", help="Python logging level, e.g. DEBUG/INFO/WARNING")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.heartbeat_interval <= 0:
        raise SystemExit("--heartbeat-interval must be > 0")

    try:
        asyncio.run(_run_demo(args))
    except KeyboardInterrupt:
        logger.info("\n[DEMO] Interrupted by user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
