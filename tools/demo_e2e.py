from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

# Allow running this script directly from repository root:
# `python tools/demo_e2e.py ...`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.adapters.cli_adapter import CliInputAdapter
from src.agent import DefaultAgentOrchestrator
from src.agent.answerer import StubAnswerer
from src.core import Core
from src.schemas.observation import (
    Actor,
    EvidenceRef,
    MessagePayload,
    Observation,
    ObservationType,
)


def _message_text(payload) -> Optional[str]:
    if isinstance(payload, MessagePayload):
        return payload.text
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            return text
    return None


class SafeCliInputAdapter(CliInputAdapter):
    """
    CLI adapter that avoids run_in_executor(input) and keeps stdin reading stable.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._line_queue: asyncio.Queue[str] = asyncio.Queue()
        self._line_consumer_task: Optional[asyncio.Task] = None
        self._stdin_thread: Optional[threading.Thread] = None
        self._stdin_stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_start(self) -> None:
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
            except Exception:
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
            except Exception:
                continue

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

            result = self._bus.publish_nowait(obs)
            if not result.ok:
                return
        except Exception:
            return


def _install_final_output_printer(core: Core) -> None:
    """
    Keep only final human-readable output; no pipeline trace logs.
    """
    bus = core.bus
    original_publish = bus.publish_nowait

    def wrapped_publish(obs: Observation):
        result = original_publish(obs)
        if not result.ok:
            return result

        is_agent_message = (
            obs.obs_type == ObservationType.MESSAGE
            and (
                (obs.source_name or "").startswith("agent:")
                or (obs.actor is not None and obs.actor.actor_id == "agent")
            )
        )
        if is_agent_message:
            text = _message_text(obs.payload)
            if text:
                print(f"\nAssistant: {text}\n")
        return result

    bus.publish_nowait = wrapped_publish  # type: ignore[assignment]


def _build_orchestrator(args: argparse.Namespace) -> DefaultAgentOrchestrator:
    if args.agent_mode == "stub":
        return DefaultAgentOrchestrator(answerer=StubAnswerer())
    return DefaultAgentOrchestrator(
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        llm_config_path=args.llm_config,
    )


async def _run_demo(args: argparse.Namespace) -> None:
    stop_event = asyncio.Event()
    core = Core(
        bus_maxsize=args.bus_maxsize,
        inbox_maxsize=args.inbox_maxsize,
        system_session_key=args.system_session_key,
        default_session_key=args.default_session_key,
        message_routing=args.message_routing,
        enable_system_fanout=args.enable_system_fanout,
        enable_session_gc=args.enable_session_gc,
        agent_orchestrator=_build_orchestrator(args),
    )

    cli_adapter = SafeCliInputAdapter(name=args.cli_adapter_name)
    cli_adapter.set_stop_event(stop_event)
    core.add_adapter(cli_adapter)
    _install_final_output_printer(core)

    core_task = asyncio.create_task(core.run_forever(), name="core.run_forever")
    stop_wait_task: Optional[asyncio.Task] = None

    try:
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
        if stop_wait_task is not None and not stop_wait_task.done():
            stop_wait_task.cancel()
        await core.shutdown()
        if not core_task.done():
            core_task.cancel()
        await asyncio.gather(core_task, return_exceptions=True)
        if stop_wait_task is not None:
            await asyncio.gather(stop_wait_task, return_exceptions=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simple E2E CLI: input text and print final assistant output."
    )
    parser.add_argument("--cli-adapter-name", default="cli_adapter")
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
    parser.add_argument("--quiet", action="store_true", help="Suppress debug logs")
    parser.add_argument("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    
    # Configure loguru - output to stdout for better Windows compatibility
    logger.remove()  # Remove default stderr handler
    
    if args.quiet:
        pass  # No output
    else:
        # Output to stdout with optional custom log level
        logger.add(
            sys.stdout,
            colorize=True,
            level=args.log_level,
        )
    
    try:
        asyncio.run(_run_demo(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
