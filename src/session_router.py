# src/session_router.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Set

# NOTE:
# 这里假设你已有 Observation 定义在 schemas/observation.py
# - obs_type: str 或 Enum（支持与字符串比较）
# - session_key: Optional[str]
# - actor: Optional[str] / str
#
# 只要字段名一致即可，无需强绑定具体类型。
from .schemas.observation import Observation
from .schemas.observation import ObservationType


# ----------------------------
# Session Inbox
# ----------------------------

@dataclass
class SessionInboxStats:
    enqueued: int = 0
    dropped: int = 0


class SessionInbox:
    """
    Per-session FIFO inbox.

    Guarantees:
    - FIFO order for successfully enqueued observations.
    - Does NOT block on put_nowait; drop-newest when full (v0 policy).
    """

    def __init__(self, *, maxsize: int = 256) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        self._queue: asyncio.Queue[Observation] = asyncio.Queue(maxsize=maxsize)
        self._stats = SessionInboxStats()

    @property
    def stats(self) -> SessionInboxStats:
        return self._stats

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def put_nowait(self, obs: Observation) -> bool:
        """
        Try enqueue without blocking.
        Returns True on success, False if dropped due to full queue.
        """
        try:
            self._queue.put_nowait(obs)
            self._stats.enqueued += 1
            return True
        except asyncio.QueueFull:
            self._stats.dropped += 1
            return False

    async def get(self) -> Observation:
        return await self._queue.get()

    def get_nowait(self) -> Observation:
        return self._queue.get_nowait()


# ----------------------------
# Session Router
# ----------------------------

class SessionRouter:
    """
    SessionRouter v0

    Role:
    - Consume Observation from an async InputBus (async iterator)
    - Resolve a deterministic session_key (if missing)
    - Route into per-session inboxes (FIFO)
    - Ensure isolation: one inbox per session_key

    Non-goals (v0):
    - No LLM/intent/memory
    - No session workers
    - No session GC / idle cleanup
    - No broadcast semantics (broadcast lives in 'system' session handler)
    """

    def __init__(
        self,
        bus: AsyncIterator[Observation],
        *,
        inbox_maxsize: int = 256,
        system_session_key: str = "system",
        default_session_key: str = "default",
        message_routing: str = "user",  # "user" or "default"
    ) -> None:
        if inbox_maxsize <= 0:
            raise ValueError("inbox_maxsize must be > 0")
        if message_routing not in ("user", "default"):
            raise ValueError("message_routing must be 'user' or 'default'")

        self._bus = bus
        self._inbox_maxsize = inbox_maxsize
        self._system_session_key = system_session_key
        self._default_session_key = default_session_key
        self._message_routing = message_routing

        self._inboxes: Dict[str, SessionInbox] = {}
        self._active_sessions: Set[str] = set()

        self._closed = False

        # Optional: track global drops for observability
        self._dropped_total = 0

    @property
    def dropped_total(self) -> int:
        return self._dropped_total

    def close(self) -> None:
        """
        Soft-close flag. `run()` will exit when bus iteration ends.
        (We do not force-close the bus here; that responsibility stays with bus owner.)
        """
        self._closed = True

    def list_active_sessions(self) -> List[str]:
        """
        Returns a stable snapshot (sorted) of active session keys seen so far.
        Useful for system-session fan-out logic in higher layers.
        """
        return sorted(self._active_sessions)

    def get_inbox(self, session_key: str) -> SessionInbox:
        """
        Get or create inbox for a given session_key.
        """
        inbox = self._inboxes.get(session_key)
        if inbox is None:
            inbox = SessionInbox(maxsize=self._inbox_maxsize)
            self._inboxes[session_key] = inbox
            self._active_sessions.add(session_key)
        return inbox

    def remove_session(self, session_key: str) -> None:
        """Remove session inbox and mark it inactive."""
        self._inboxes.pop(session_key, None)
        self._active_sessions.discard(session_key)

    def resolve_session_key(self, obs: Observation) -> str:
        """
        Deterministic session key resolver (v0 policy).

        1) If obs.session_key exists -> use it
        2) Else:
           - MESSAGE -> user:{actor}  (or default) depending on message_routing
           - Others  -> system_session_key
        """
        sk = getattr(obs, "session_key", None)
        if sk:
            return sk

        obs_type = getattr(obs, "obs_type", None)

        is_message = False
        if isinstance(obs_type, ObservationType):
            is_message = obs_type == ObservationType.MESSAGE
        else:
            # Support both Enum and str by normalizing to str for comparison
            obs_type_str = str(obs_type).strip().lower() if obs_type is not None else ""
            is_message = obs_type_str.endswith("message") or obs_type_str == "message"

        if is_message:
            if self._message_routing == "default":
                return self._default_session_key

            actor_id: str = ""
            actor = getattr(obs, "actor", None)
            if isinstance(actor, str):
                actor_id = actor.strip()
            elif actor is not None and hasattr(actor, "actor_id"):
                raw_actor_id = getattr(actor, "actor_id", None)
                actor_id = str(raw_actor_id).strip() if raw_actor_id is not None else ""

            if actor_id:
                return f"user:{actor_id}"
            return self._default_session_key

        return self._system_session_key

    async def run(self) -> None:
        """
        Main routing loop.

        Behavior:
        - Reads from bus until it ends.
        - Routes each obs into per-session inbox.
        - If inbox is full -> drop newest (count in inbox + router dropped_total).
        - Never raises due to inbox full; never blocks on enqueue.
        """
        async for obs in self._bus:
            if self._closed:
                # Soft-close: stop routing new items once flagged.
                break

            sk = self.resolve_session_key(obs)
            inbox = self.get_inbox(sk)

            ok = inbox.put_nowait(obs)
            if not ok:
                self._dropped_total += 1
                # v0: silently drop newest.
                # v1 option: create ALERT obs routed to system session.

        # run() ends gracefully when bus ends or router is closed.
        return
