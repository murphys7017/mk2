"""
Agent 类型定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from ..schemas.observation import Observation
from ..gate.types import GateDecision, GateHint
from ..session_state import SessionState


# ============================================================
# Orchestrator v2 MVP 类型定义
# ============================================================

@dataclass
class AgentRequest:
    """Agent 处理请求（MVP 版）"""
    obs: Observation
    gate_decision: GateDecision
    session_state: SessionState
    now: datetime
    gate_hint: Optional[GateHint] = None
    
    def __post_init__(self):
        if self.gate_hint is None and self.gate_decision:
            self.gate_hint = self.gate_decision.hint


@dataclass
class InfoPlan:
    """信息需求计划"""
    sources: List[str] = field(default_factory=list)  # ["time", "memory", "kb", ...]
    budget: Dict[str, Any] = field(default_factory=dict)  # {"time_ms": 2000, ...}
    tool_calls: Optional[List[str]] = None  # 新增：规划的工具调用


@dataclass
class EvidenceItem:
    """单条证据"""
    source: str  # "time", "memory", "kb", etc.
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidencePack:
    """证据包"""
    items: List[EvidenceItem] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)  # {"total_items": 2, "sources": [...]}


@dataclass
class AnswerDraft:
    """回答草稿"""
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)  # {"confidence": 0.8, "method": "llm", ...}


@dataclass
class AnswerSpec:
    """回答规格"""
    model: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)  # {"temperature": 0.7, "max_tokens": 256}


@dataclass
class AgentOutcome:
    """Agent 处理结果（MVP 版）"""
    emit: List[Observation] = field(default_factory=list)  # 要发送的观察（通常是回复）
    trace: Dict[str, Any] = field(default_factory=dict)  # 执行跟踪信息
    error: Optional[str] = None  # 错误信息（如有）


# ============================================================
# 向后兼容类型（保留，支持旧 Planner/Agent 代码）
# ============================================================

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
    """Agent 响应（旧接口，保留兼容性）"""
    emit: List[Observation] = field(default_factory=list)  # 要发送的观察
    success: bool = True
    error: Optional[str] = None
