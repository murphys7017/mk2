"""
PostProcessor: Agent 回复后处理
"""
from __future__ import annotations

from typing import Protocol

from .types import AgentRequest, AnswerDraft, EvidencePack
from ..schemas.observation import Observation


class PostProcessor(Protocol):
    """PostProcessor 接口"""
    
    async def after_reply(
        self,
        req: AgentRequest,
        draft: AnswerDraft,
        evidence: EvidencePack,
    ) -> list[Observation]:
        """回复后处理（例如日志、监控、衍生观察等）"""
        ...


class NoopPostProcessor:
    """空操作 PostProcessor（什么都不做）"""
    
    async def after_reply(
        self,
        req: AgentRequest,
        draft: AnswerDraft,
        evidence: EvidencePack,
    ) -> list[Observation]:
        """返回空列表（无额外观察）"""
        return []
