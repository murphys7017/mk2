"""
AgentOrchestrator MVP 单测
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from loguru import logger

import pytest

from src.agent.orchestrator import DefaultAgentOrchestrator
from src.agent.answerer import StubAnswerer
from src.agent.types import AgentRequest
from src.gate.types import GateDecision, Scene, GateAction
from src.session_router import SessionState
from src.schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    MessagePayload,
)



@pytest.fixture
def orchestrator():
    """创建 Orchestrator 实例（使用 Stub 避免 LLM 依赖）"""
    return DefaultAgentOrchestrator(
        answerer=StubAnswerer()  # 用 stub 避免网络调用
    )


@pytest.fixture
def test_obs():
    """创建测试观察"""
    return Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test_input",
        source_kind=SourceKind.EXTERNAL,
        session_key="test_session",
        actor=Actor(actor_id="test_user", actor_type="user"),
        payload=MessagePayload(text="现在几点"),
    )


@pytest.fixture
def test_state():
    """创建测试会话状态"""
    return SessionState(session_key="test_session")


@pytest.fixture
def test_decision():
    """创建测试网关决策"""
    return GateDecision(
        action=GateAction.DELIVER,
        scene=Scene.DIALOGUE,
        session_key="test_session",
    )


@pytest.mark.asyncio
async def test_orchestrator_basic_flow(orchestrator, test_obs, test_state, test_decision):
    """测试 Orchestrator 基础流程"""
    req = AgentRequest(
        obs=test_obs,
        gate_decision=test_decision,
        session_state=test_state,
        now=datetime.now(timezone.utc),
    )
    
    # 执行 handle
    outcome = await orchestrator.handle(req)
    
    # 验证：emit 至少 1 条观察
    assert len(outcome.emit) >= 1, "Should emit at least 1 observation"
    
    # 验证：emit 的都是 MESSAGE 类型
    for obs in outcome.emit:
        assert obs.obs_type == ObservationType.MESSAGE
        assert obs.source_kind == SourceKind.INTERNAL
        assert obs.session_key == "test_session"
    
    # 验证：trace 包含完整信息
    assert "start_ts" in outcome.trace
    assert "end_ts" in outcome.trace
    assert "elapsed_ms" in outcome.trace
    assert "steps" in outcome.trace
    
    # 验证：steps 中有 planning、evidence、answering 等
    steps = outcome.trace["steps"]
    assert "planning" in steps
    assert "evidence" in steps
    assert "answering" in steps
    assert "speaking" in steps
    
    # 验证：无错误
    assert outcome.error is None, f"Should have no error, but got: {outcome.error}"
    
    print(f"✓ Basic flow passed")
    print(f"  Trace: {outcome.trace}")
    print(f"  Response: {outcome.emit[0].payload.text if outcome.emit else '(empty)'}")


@pytest.mark.asyncio
async def test_orchestrator_with_time_keyword(orchestrator, test_state, test_decision):
    """测试 Orchestrator 识别时间关键词"""
    # 包含时间关键词的输入
    test_obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test_input",
        source_kind=SourceKind.EXTERNAL,
        session_key="test_session",
        actor=Actor(actor_id="test_user", actor_type="user"),
        payload=MessagePayload(text="现在几点钟？"),
    )
    
    req = AgentRequest(
        obs=test_obs,
        gate_decision=test_decision,
        session_state=test_state,
        now=datetime.now(timezone.utc),
    )
    
    outcome = await orchestrator.handle(req)
    
    # 验证：plan 应该识别到 time 源
    assert "planning" in outcome.trace["steps"]
    planning_info = outcome.trace["steps"]["planning"]
    assert "sources" in planning_info
    assert "time" in planning_info["sources"]
    
    # 验证：evidence 应该包含 time 信息
    assert "evidence" in outcome.trace["steps"]
    evidence_info = outcome.trace["steps"]["evidence"]
    assert evidence_info["items_count"] > 0
    
    # 验证：回复中应该包含 stub_evidence_from_time 或类似字样
    response_text = outcome.emit[0].payload.text if outcome.emit else ""
    assert "time" in response_text.lower() or "stub" in response_text.lower()
    
    print(f"✓ Time keyword passed")
    print(f"  Planning sources: {planning_info['sources']}")
    print(f"  Evidence items: {evidence_info['items_count']}")


@pytest.mark.asyncio
async def test_orchestrator_emit_structure(orchestrator, test_obs, test_state, test_decision):
    """测试 Orchestrator emit 的结构正确性"""
    req = AgentRequest(
        obs=test_obs,
        gate_decision=test_decision,
        session_state=test_state,
        now=datetime.now(timezone.utc),
    )
    
    outcome = await orchestrator.handle(req)
    
    # 验证 emit 的观察构造正确
    assert len(outcome.emit) > 0
    for obs in outcome.emit:
        assert obs.obs_id  # 应该有 obs_id
        assert obs.obs_type == ObservationType.MESSAGE
        assert obs.source_name.startswith("agent:")
        assert obs.source_kind == SourceKind.INTERNAL
        assert obs.session_key == "test_session"
        assert obs.actor.actor_type == "system"
        assert isinstance(obs.payload, MessagePayload)
        assert isinstance(obs.payload.text, str)
        assert len(obs.payload.text) > 0
    
    print(f"✓ Emit structure passed")


@pytest.mark.asyncio
async def test_orchestrator_error_handling(orchestrator, test_state, test_decision):
    """测试 Orchestrator 错误处理能力"""
    # 创建一个会导致错误的请求（无效 payload）
    bad_obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name="test_input",
        source_kind=SourceKind.EXTERNAL,
        session_key="test_session",
        actor=Actor(actor_id="test_user", actor_type="user"),
        payload=MessagePayload(text=""),  # 空文本，可能导致某些步骤失败
    )
    
    req = AgentRequest(
        obs=bad_obs,
        gate_decision=test_decision,
        session_state=test_state,
        now=datetime.now(timezone.utc),
    )
    
    outcome = await orchestrator.handle(req)
    
    # 验证：即使有错误也应该返回 fallback 回复
    assert len(outcome.emit) >= 1, "Should return fallback observation"
    assert outcome.emit[0].obs_type == ObservationType.MESSAGE
    
    # 验证：trace 中应该记录错误
    assert "steps" in outcome.trace
    
    print(f"✓ Error handling passed")
    print(f"  Fallback response: {outcome.emit[0].payload.text if outcome.emit else '(empty)'}")


@pytest.mark.asyncio
async def test_orchestrator_trace_timing(orchestrator, test_obs, test_state, test_decision):
    """测试 Orchestrator 的性能追踪"""
    req = AgentRequest(
        obs=test_obs,
        gate_decision=test_decision,
        session_state=test_state,
        now=datetime.now(timezone.utc),
    )
    
    outcome = await orchestrator.handle(req)
    
    # 验证：trace 中有时间戳和耗时
    assert "start_ts" in outcome.trace
    assert "end_ts" in outcome.trace
    assert "elapsed_ms" in outcome.trace
    
    elapsed_ms = outcome.trace["elapsed_ms"]
    assert elapsed_ms >= 0, f"Elapsed time should be non-negative, got {elapsed_ms}ms"
    assert elapsed_ms < 10000, f"Should complete in < 10 seconds, got {elapsed_ms}ms"
    
    print(f"✓ Trace timing passed: {elapsed_ms:.1f}ms")


if __name__ == "__main__":
    # 可以直接运行单个测试
    asyncio.run(test_orchestrator_basic_flow(
        DefaultAgentOrchestrator(),
        Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test_input",
            source_kind=SourceKind.EXTERNAL,
            session_key="test_session",
            actor=Actor(actor_id="test_user", actor_type="user"),
            payload=MessagePayload(text="现在几点"),
        ),
        SessionState(session_key="test_session"),
        GateDecision(
            action=GateAction.DELIVER,
            scene=Scene.DIALOGUE,
            session_key="test_session",
        )
    ))
