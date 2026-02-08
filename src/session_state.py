# src/session_state.py
# =========================
# Session 运行态状态（轻量）
# Session Runtime State (lightweight)
# =========================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

from .schemas.observation import Observation


@dataclass
class SessionState:
    """
    Session 的轻量运行态状态，持有：
    - 会话基本信息（session_key, 创建时间）
    - 处理统计（总数、错误数）
    - 最近的 observations（deque，max 20）
    
    不是 memory 系统，仅供 Core worker 和测试使用。
    """
    session_key: str
    created_at: float = field(default_factory=time.time)
    last_active_at: Optional[float] = field(default=None)
    processed_total: int = 0
    error_total: int = 0
    recent_obs: deque = field(default_factory=lambda: deque(maxlen=20))

    def touch(self) -> None:
        """更新最后活跃时间"""
        self.last_active_at = time.time()

    def record(self, obs: Observation) -> None:
        """
        记录一条 observation：
        - 更新 last_active_at
        - processed_total++
        - 将 obs 加入 recent_obs
        """
        self.touch()
        self.processed_total += 1
        self.recent_obs.append(obs)

    def record_error(self) -> None:
        """
        记录一个错误：
        - 更新 last_active_at
        - error_total++
        """
        self.touch()
        self.error_total += 1

    def idle_seconds(self) -> Optional[float]:
        """
        返回 idle 秒数（当前时间 - last_active_at）。
        若从未活跃过返回 None。
        """
        if self.last_active_at is None:
            return None
        return time.time() - self.last_active_at
