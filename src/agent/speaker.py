"""
Speaker: 将回答转换为 Observation
"""
from __future__ import annotations

from typing import Protocol

from .types import AgentRequest, AnswerDraft
from ..schemas.observation import Observation, ObservationType, Actor, MessagePayload, SourceKind


class Speaker(Protocol):
    """Speaker 接口"""
    
    async def render(self, req: AgentRequest, draft: AnswerDraft) -> list[Observation]:
        """将回答草稿转换为 Observation 列表"""
        ...


class DefaultSpeaker:
    """默认 Speaker（生成 MESSAGE 类型 Observation）"""
    
    async def render(self, req: AgentRequest, draft: AnswerDraft) -> list[Observation]:
        """
        根据回答草稿生成 Observation（通常是 Assistant 回复）
        """
        # 构造 Assistant 回复观察
        response_obs = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="agent:speaker",
            source_kind=SourceKind.INTERNAL,
            session_key=req.obs.session_key,  # 继承原 obs 的 session_key
            actor=Actor(
                actor_id="agent",
                actor_type="system",
                display_name="Agent Assistant"
            ),
            payload=MessagePayload(text=draft.text),
        )
        response_obs.metadata = {
            "agent_method": draft.meta.get("method", "unknown"),
            "evidence_count": draft.meta.get("evidence_count", 0),
        }
        
        return [response_obs]
