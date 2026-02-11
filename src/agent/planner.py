"""
RulePlanner: 基于规则的计划器
"""
from __future__ import annotations

from .types import AgentRequest, Plan, Step
from ..schemas.observation import MessagePayload


class RulePlanner:
    """基于规则的简单计划器"""
    
    TIME_KEYWORDS = ["时间", "几点", "now", "time", "当前时间"]
    
    def build_plan(self, req: AgentRequest) -> Plan:
        """根据请求构建执行计划"""
        text = self._extract_text(req)
        
        # 检查是否包含时间关键词
        if self._contains_time_keyword(text):
            return Plan(
                steps=[Step(type="SKILL", target="get_time")],
                reason="time_intent_detected"
            )
        
        # 默认走对话 agent
        return Plan(
            steps=[Step(type="AGENT", target="dialogue")],
            reason="default_dialogue"
        )
    
    def _extract_text(self, req: AgentRequest) -> str:
        """提取文本内容"""
        if isinstance(req.obs.payload, MessagePayload):
            return (req.obs.payload.text or "").strip()
        return ""
    
    def _contains_time_keyword(self, text: str) -> bool:
        """检查文本是否包含时间关键词"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.TIME_KEYWORDS)
