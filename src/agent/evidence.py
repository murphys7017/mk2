"""
EvidenceRunner: 根据信息计划收集证据
"""
from __future__ import annotations

import time
from typing import Protocol

from .types import AgentRequest, InfoPlan, EvidencePack, EvidenceItem
from ..session_state import SessionState


class EvidenceRunner(Protocol):
    """EvidenceRunner 接口"""
    
    async def gather(self, req: AgentRequest, info_plan: InfoPlan) -> EvidencePack:
        """根据信息计划收集证据"""
        ...


class StubEvidenceRunner:
    """Stub EvidenceRunner（返回 mock 证据）"""
    
    async def gather(self, req: AgentRequest, info_plan: InfoPlan) -> EvidencePack:
        """
        根据 info_plan 收集证据（stub 版本）
        """
        items = []
        
        # 根据请求的 sources 生成 stub 证据
        for source in info_plan.sources:
            if source == "time":
                # Mock 时间证据
                current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                items.append(EvidenceItem(
                    source="time",
                    content=f"Current time: {current_time}",
                    metadata={"type": "system_time"}
                ))
            
            elif source == "memory":
                # Mock 内存证据（从 SessionState 中简单提取）
                memory_summary = self._extract_memory_summary(req.session_state)
                if memory_summary:
                    items.append(EvidenceItem(
                        source="memory",
                        content=memory_summary,
                        metadata={"type": "session_memory"}
                    ))
            
            else:
                # 其他源的 stub 回复
                items.append(EvidenceItem(
                    source=source,
                    content=f"(stub_evidence_from_{source})",
                    metadata={"type": "unknown"}
                ))
        
        return EvidencePack(
            items=items,
            stats={
                "total_items": len(items),
                "sources": info_plan.sources,
            }
        )
    
    def _extract_memory_summary(self, state: SessionState) -> str:
        """从 SessionState 提取简单的内存摘要"""
        if not state.recent_obs:
            return "(no_recent_memory)"
        
        # 简单地列出最近 3 条 obs 的摘要
        from ..schemas.observation import MessagePayload
        
        summaries = []
        for obs in list(state.recent_obs)[-3:]:
            if isinstance(obs.payload, MessagePayload) and obs.payload.text:
                text = obs.payload.text[:50]  # 截断为 50 字符
                summaries.append(f"- {text}")
        
        if summaries:
            return "Recent context:\n" + "\n".join(summaries)
        return "(no_recent_memory)"
