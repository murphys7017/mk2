"""Planner 相关类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class PlannerSignals:
    """从输入文本抽取的规则信号。"""

    text: str = ""
    has_code_signal: bool = False
    has_plan_signal: bool = False
    has_creative_signal: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
