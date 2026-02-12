"""
Answerer: 根据请求 + 证据生成回答
"""
from __future__ import annotations

from typing import Protocol, Optional, Any, Dict

from .types import AgentRequest, EvidencePack, AnswerDraft, AnswerSpec


class Answerer(Protocol):
    """Answerer 接口"""
    
    async def answer(
        self,
        req: AgentRequest,
        evidence: EvidencePack,
        answer_spec: AnswerSpec,
    ) -> AnswerDraft:
        """根据请求和证据生成回答"""
        ...


class StubAnswerer:
    """Stub Answerer（返回简单的 mock 回答）"""
    
    async def answer(
        self,
        req: AgentRequest,
        evidence: EvidencePack,
        answer_spec: AnswerSpec,
    ) -> AnswerDraft:
        """
        根据请求 + 证据生成回答（stub 版本）
        """
        from ..schemas.observation import MessagePayload
        
        # 提取用户输入
        user_text = ""
        if isinstance(req.obs.payload, MessagePayload):
            user_text = req.obs.payload.text or ""
        
        # 简单拼接：用户输入 + 证据
        draft_text = f"ACK: {user_text}"
        
        if evidence.items:
            evidence_str = " | Evidence: " + "; ".join(
                f"{item.source}={item.content}"
                for item in evidence.items
            )
            draft_text += evidence_str
        
        return AnswerDraft(
            text=draft_text,
            meta={
                "method": "stub",
                "evidence_count": len(evidence.items),
                "model": answer_spec.model,
            }
        )


class LLMAnswerer:
    """真实 LLM Answerer（调用 LLMGateway）"""
    
    def __init__(
        self,
        provider: str = "bailian",
        model: str = "qwen-max",
        config_path: str = "config/llm.yaml",
    ) -> None:
        """初始化 LLM Answerer"""
        from ..llm import LLMGateway
        
        self._gateway = LLMGateway.from_config(
            provider=provider,
            model=model,
            config_path=config_path,
        )
    
    async def answer(
        self,
        req: AgentRequest,
        evidence: EvidencePack,
        answer_spec: AnswerSpec,
    ) -> AnswerDraft:
        """
        根据请求 + 证据通过 LLM 生成回答（真实实现）
        """
        from ..schemas.observation import MessagePayload
        
        # 提取用户输入
        user_text = ""
        if isinstance(req.obs.payload, MessagePayload):
            user_text = req.obs.payload.text or ""
        
        # 构造系统提示和用户消息
        system_prompt = "你是一个简洁而有帮助的助手。"
        
        # 如果有证据，添加到系统提示中
        if evidence.items:
            evidence_text = "\n".join(
                f"【{item.source}】{item.content}"
                for item in evidence.items
            )
            system_prompt += f"\n\n已获得的背景信息：\n{evidence_text}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        
        # 调用 LLM
        answer_text = self._gateway.call(
            messages,
            temperature=0.2,
            max_tokens=512,
        )
        
        return AnswerDraft(
            text=answer_text,
            meta={
                "method": "llm",
                "evidence_count": len(evidence.items),
                "model": answer_spec.model or getattr(self._gateway, "_model_name", "unknown"),
            }
        )
