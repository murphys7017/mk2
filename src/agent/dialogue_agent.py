"""
SimpleDialogueAgent: 简单对话代理
"""
from __future__ import annotations

from typing import List, Dict

from .types import AgentRequest
from .llm import LLMClient
from ..schemas.observation import MessagePayload


class SimpleDialogueAgent:
    """简单对话代理"""
    
    def __init__(self, llm: LLMClient):
        self.llm = llm
    
    def reply(self, req: AgentRequest) -> str:
        """生成回复"""
        messages = self._build_messages(req)
        return self.llm.call(messages)
    
    def _build_messages(self, req: AgentRequest) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = []
        
        # 可选：系统提示
        # messages.append({
        #     "role": "system",
        #     "content": "你是一个有帮助的助手。"
        # })
        
        # 用户消息
        user_text = ""
        if isinstance(req.obs.payload, MessagePayload):
            user_text = req.obs.payload.text or ""
        
        messages.append({
            "role": "user",
            "content": user_text
        })
        
        return messages
