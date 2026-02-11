"""
Agent 类型定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Literal

from ..schemas.observation import Observation
from ..gate.types import GateDecision
from ..session_state import SessionState


@dataclass
class AgentRequest:
    """Agent 处理请求"""
    obs: Observation
    decision: GateDecision
    state: SessionState
    now: datetime


@dataclass
class Step:
    """执行步骤"""
    type: Literal["SKILL", "AGENT", "TOOL"]
    target: str  # skill/agent/tool 的名称
    params: dict = field(default_factory=dict)


@dataclass
class Plan:
    """执行计划"""
    steps: List[Step] = field(default_factory=list)
    reason: str = ""


@dataclass
class AgentResponse:
    """Agent 响应"""
    emit: List[Observation] = field(default_factory=list)  # 要发送的观察
    success: bool = True
    error: Optional[str] = None
