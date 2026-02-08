# src/input_bus.py
# =========================
# 异步输入总线（Core 侧 async 消费 + Adapter 侧同步投递）
# Async InputBus (async consume for Core + sync publish for Adapters)
# =========================

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, AsyncIterator

from .schemas.observation import Observation


@dataclass(frozen=True)
class PublishResult:
    """
    中文：同步投递结果（给 Adapter 用）
    English: sync publish result (for adapters)
    """
    ok: bool
    dropped: bool = False
    reason: Optional[str] = None


class InputBusClosed(Exception):
    pass


class AsyncInputBus:
    """
    中文：
      AsyncInputBus 同时服务两端：
      - Adapter 侧（同步）：publish_nowait(obs) -> PublishResult
      - Core 侧（异步）：async for obs in bus / await bus.get()

      设计：
      - 队列满默认丢弃（drop_when_full=True）——生命体风
      - Core 可 close()，迭代自然结束

    English:
      Dual-mode bus:
      - sync publish_nowait for adapters
      - async consume for core
    """

    def __init__(
        self,
        *,
        maxsize: int = 1000,
        drop_when_full: bool = True,
    ) -> None:
        self._queue: asyncio.Queue[Observation] = asyncio.Queue(maxsize=maxsize)
        self._closed: bool = False

        self.drop_when_full = drop_when_full

        # basic metrics
        self.published_total: int = 0
        self.dropped_total: int = 0
        self.consumed_total: int = 0

        self.created_at = datetime.now(timezone.utc)

    # -------------------------
    # 生命周期 / lifecycle
    # -------------------------

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def size(self) -> int:
        return self._queue.qsize()

    # -------------------------
    # Adapter 侧：同步投递（关键）
    # Sync publish for adapters (key)
    # -------------------------

    def publish_nowait(self, obs: Observation) -> PublishResult:
        """
        中文：
          同步、不阻塞投递。
          - 总线关闭：返回 dropped
          - 队列满且 drop_when_full=True：丢弃
          - 否则 put_nowait（若仍满则丢）

        English:
          Non-blocking synchronous publish.
        """
        if self._closed:
            return PublishResult(ok=False, dropped=True, reason="closed")

        obs.validate()
        self.published_total += 1

        if self.drop_when_full and self._queue.full():
            self.dropped_total += 1
            return PublishResult(ok=False, dropped=True, reason="queue_full")

        try:
            self._queue.put_nowait(obs)
            return PublishResult(ok=True)
        except asyncio.QueueFull:
            self.dropped_total += 1
            return PublishResult(ok=False, dropped=True, reason="queue_full")

    # -------------------------
    # Core 侧：异步消费
    # Async consume for core
    # -------------------------

    async def get(self, timeout: Optional[float] = None) -> Optional[Observation]:
        """
        中文：
          获取一条 Observation
          - timeout=None：一直等
          - timeout=0：立即返回（几乎不会用 async 这样）
          - 超时返回 None
          - close 且队列空：返回 None

        English:
          Get one observation.
        """
        if self._closed and self._queue.empty():
            return None

        try:
            if timeout is None:
                obs = await self._queue.get()
            else:
                obs = await asyncio.wait_for(self._queue.get(), timeout)
            self.consumed_total += 1
            return obs
        except asyncio.TimeoutError:
            return None

    def __aiter__(self) -> "AsyncInputBus":
        """Return self as an async iterator (Core can `async for obs in bus`)."""
        return self

    async def __anext__(self) -> Observation:
        """Async iterator protocol.

        Stops when the bus is closed AND the queue is drained.
        """
        while True:
            obs = await self.get(timeout=0.5)
            if obs is None:
                if self._closed and self._queue.empty():
                    raise StopAsyncIteration
                continue
            return obs
