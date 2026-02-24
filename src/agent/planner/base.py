"""Planner 协议定义。"""

from __future__ import annotations

from typing import Protocol

from ..types import AgentRequest, TaskPlan
from .types import PlannerInputView


class Planner(Protocol):
    """可插拔 Planner 接口。"""

    kind: str

    async def plan(self, req: AgentRequest, view: PlannerInputView | None = None) -> TaskPlan:
        """基于输入请求生成 TaskPlan。"""
        ...
