"""
RulePlanner: 基于规则的计划器
"""
from __future__ import annotations

from typing import Optional, Protocol

from .types import AgentRequest, Plan, Step, InfoPlan, AnswerSpec
from ..schemas.observation import MessagePayload
from ..gate.types import GateHint


# ============================================================
# MVP 接口（新）
# ============================================================

class Planner(Protocol):
    """Planner MVP 接口"""
    
    async def plan(self, req: AgentRequest, gate_hint: Optional[GateHint] = None) -> tuple[InfoPlan, AnswerSpec]:
        """生成信息计划和回答规格"""
        ...


# ============================================================
# RulePlanner 实现（同时支持新旧接口）
# ============================================================

class RulePlanner:
    """基于规则的简单计划器（同时支持旧 build_plan 和新 plan 接口）"""
    
    TIME_KEYWORDS = ["时间", "几点", "now", "time", "当前时间", "现在几点", "what time"]
    MEMORY_KEYWORDS = ["记得", "还记得", "remember", "我们之前"]
    
    # ============================================================
    # 新接口（MVP v2）
    # ============================================================
    
    async def plan(self, req: AgentRequest, gate_hint: Optional[GateHint] = None) -> tuple[InfoPlan, AnswerSpec]:
        """根据请求构建信息计划和回答规格，遵守 Gate 的预算约束"""
        text = self._extract_text(req)
        text_lower = text.lower()
        
        # 获取预算约束
        budget = gate_hint.budget if gate_hint else None
        
        # 判断信息来源
        sources = []
        
        # ✓ 必须遵守：evidence_allowed
        if budget and not budget.evidence_allowed:
            # 不允许取证，只能用 memory / direct
            sources = ["memory"]
        else:
            # 允许取证 - 根据输入内容判断
            if any(kw in text_lower for kw in self.TIME_KEYWORDS):
                sources.append("time")
            
            if any(kw in text_lower for kw in self.MEMORY_KEYWORDS):
                sources.append("memory")
            
            # 如果相关度高，可以尝试 kb 搜索
            if budget and budget.can_search_kb:
                # 启发式：长文本或特定关键词才搜索 kb
                if len(text) > 50 or any(kw in text_lower for kw in ["知道", "告诉", "查", "ask", "search"]):
                    sources.append("kb")
        
        # 默认总是查询内存
        if not sources:
            sources = ["memory"]
        
        # ✓ 必须遵守：max_tool_calls
        tool_calls = []
        if budget and budget.max_tool_calls > 0:
            # 可以规划工具调用（不要超过 max_tool_calls）
            if budget.can_call_tools:
                # 简单启发式：是否需要工具
                if any(kw in text_lower for kw in ["天气", "查", "搜索", "weather", "search"]):
                    # 最多规划 min(max_tool_calls, 1) 个工具
                    tool_calls = ["search_tool"] if budget.max_tool_calls >= 1 else []
        # else: tool_calls 为空（budget 限制或不允许工具）
        
        info_plan = InfoPlan(
            sources=sources,
            budget={
                "time_ms": budget.time_ms if budget else 1500,
                "max_tokens": budget.max_tokens if budget else 512,
                "evidence_allowed": budget.evidence_allowed if budget else True,
                "max_tool_calls": len(tool_calls),
                "max_parallel": budget.max_parallel if budget else 1,
            },
            tool_calls=tool_calls if tool_calls else None,
        )
        
        # 根据预算决定回答规格
        model_tier = gate_hint.model_tier if gate_hint else "low"
        answer_spec = AnswerSpec(
            model=None,  # 先不指定，由 answerer 决定
            params={
                "model_tier": model_tier,
                "max_tokens": budget.max_tokens if budget else 512,
            }
        )
        
        return info_plan, answer_spec
    
    # ============================================================
    # 旧接口（向后兼容）
    # ============================================================
    
    def build_plan(self, req: AgentRequest) -> Plan:
        """根据请求构建执行计划（旧接口，向后兼容）"""
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
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _extract_text(self, req: AgentRequest) -> str:
        """提取文本内容"""
        if isinstance(req.obs.payload, MessagePayload):
            return (req.obs.payload.text or "").strip()
        return ""
    
    def _contains_time_keyword(self, text: str) -> bool:
        """检查文本是否包含时间关键词"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.TIME_KEYWORDS)
