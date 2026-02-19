"""
E2E 集成测试：用户消息 → Gate DELIVER → Agent(LLM) → 回流到 SessionState
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from loguru import logger

import pytest

from src.core import Core
from src.schemas.observation import (
    Observation,
    ObservationType,
    SourceKind,
    Actor,
    MessagePayload,
)

@pytest.mark.integration
@pytest.mark.asyncio
async def test_core_agent_e2e_user_to_response():
    """
    E2E 测试：用户输入 → Gate DELIVER → Agent(LLM) → emit 回流 → SessionState 看到回复
    
    运行命令：
    uv run pytest tests/test_core_agent_e2e_live.py::test_core_agent_e2e_user_to_response -v -s
    """
    logger.info("Starting E2E test: user message → agent response")
    
    # 1. 创建 Core
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,  # 避免 tick 干扰
    )
    
    # 2. 启动 Core
    run_task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.2)  # 等待 Core 启动
    
    try:
        # 3. 投递用户消息
        session_key = "dm:e2e_test"
        user_message = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test_input",
            source_kind=SourceKind.EXTERNAL,
            session_key=session_key,
            actor=Actor(
                actor_id="test_user",
                actor_type="user",
                display_name="Test User"
            ),
            payload=MessagePayload(text="你好，请问现在几点？"),
        )
        
        payload_text = user_message.payload.text if isinstance(user_message.payload, MessagePayload) else "unknown"
        logger.info(f"Publishing user message: {payload_text}")
        core.bus.publish_nowait(user_message)
        
        # 4. 等待处理（给 LLM 网络调用留时间）
        # 包括：routing → gate decision → agent orchestrator → LLM call → emit → 存储到 state
        # 使用 polling + timeout 代替固定 sleep，提高可靠性
        max_wait_seconds = 5.0
        start_time = asyncio.get_event_loop().time()
        agent_messages = []
        while asyncio.get_event_loop().time() - start_time < max_wait_seconds:
            state = core.get_state(session_key)
            agent_messages = [
                obs for obs in state.recent_obs
                if obs.obs_type == ObservationType.MESSAGE
                and obs.source_name.startswith("agent")
                and obs.payload.text
                and obs.payload.text.strip()
            ]
            if agent_messages:
                break
            await asyncio.sleep(0.1)  # 每 100ms 检查一次
        
        # 5. 变量提前，用于下面断言
        if not agent_messages:
            # 超时仍未收到 agent 消息，获取一次 state
            state = core.get_state(session_key)
        
        # 6. 断言：SessionState.recent_obs 中应该出现 agent 的 MESSAGE
        
        assert len(agent_messages) > 0, (
            f"Expected agent message in recent_obs, but found none. "
            f"Recent obs: {[(o.obs_type, o.actor.actor_type) for o in state.recent_obs]}"
        )
        
        # 7. 验证响应内容
        agent_reply = agent_messages[0]
        assert agent_reply.source_name.startswith("agent"), (
            f"Expected agent source_name, got {agent_reply.source_name}"
        )
        assert len(agent_reply.payload.text) > 0, "Agent reply should not be empty"
        
        logger.info(f"✓ Agent reply: {agent_reply.payload.text[:100]}")
        
        # 8. 额外验证：agent 回复不应该再次触发 agent（防止死循环）
        # 等待一段时间，确认没有新的 agent 消息
        initial_agent_count = len(agent_messages)
        logger.info(f"Initial agent message count: {initial_agent_count}")
        
        # Polling 检查 2 秒内是否有新的 agent 消息
        # 如果在这段时间内有新消息出现，说明可能有循环
        check_duration = 2.0
        check_start = asyncio.get_event_loop().time()
        loop_detected = False
        
        while asyncio.get_event_loop().time() - check_start < check_duration:
            state = core.get_state(session_key)
            new_agent_messages = [
                obs for obs in state.recent_obs
                if obs.obs_type == ObservationType.MESSAGE
                and obs.source_name.startswith("agent")
            ]
            if len(new_agent_messages) > initial_agent_count:
                loop_detected = True
                logger.warning(f"Loop detected: agent messages increased from {initial_agent_count} to {len(new_agent_messages)}")
                break
            await asyncio.sleep(0.1)  # 每 100ms 检查一次
        
        assert not loop_detected, (
            f"Possible loop detected: agent messages increased during check period. "
            f"Initial: {initial_agent_count}, Final: {len(new_agent_messages) if loop_detected else initial_agent_count}"
        )
        
        logger.info("✓ E2E test passed: user → gate → agent(llm) → response ✓")
    
    finally:
        # 清理
        run_task.cancel()
        try:
            await asyncio.gather(run_task, return_exceptions=True)
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_core_agent_with_context():
    """
    E2E 测试：验证 Agent 能看到 SessionState 的上下文
    
    验证流程：
    1. 投递第一句话："你叫什么"
    2. Agent 回复（这会进入 state.recent_obs）
    3. 投递第二句话："我刚才问了什么" 
    4. Agent 应该能看到 state.recent_obs 中的历史，给出相关回复
    """
    logger.info("Starting E2E test: agent with context awareness")
    
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
        enable_system_fanout=False,
    )
    
    run_task = asyncio.create_task(core.run_forever())
    await asyncio.sleep(0.2)
    
    try:
        session_key = "dm:context_test"
        
        # 第一条消息
        msg1 = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test_input",
            source_kind=SourceKind.EXTERNAL,
            session_key=session_key,
            actor=Actor(
                actor_id="test_user",
                actor_type="user",
                display_name="Test User"
            ),
            payload=MessagePayload(text="你好，你叫什么名字？"),
        )
        
        payload_text_1 = msg1.payload.text if isinstance(msg1.payload, MessagePayload) else "unknown"
        logger.info(f"Publishing message 1: {payload_text_1}")
        core.bus.publish_nowait(msg1)
        
        # 等待 Agent 处理第一条消息（用 polling）
        max_wait_seconds = 5.0
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < max_wait_seconds:
            state = core.get_state(session_key)
            agent_replies = [obs for obs in state.recent_obs if obs.source_name.startswith("agent")]
            if agent_replies:
                break
            await asyncio.sleep(0.1)
        
        state = core.get_state(session_key)
        initial_obs_count = len(state.recent_obs)
        logger.info(f"After first message: {initial_obs_count} observations in state")
        
        # 验证有 agent 回复
        agent_replies = [
            obs for obs in state.recent_obs
            if obs.source_name.startswith("agent")
        ]
        assert len(agent_replies) >= 1, "Should have at least one agent reply"
        
        # 第二条消息
        msg2 = Observation(
            obs_type=ObservationType.MESSAGE,
            source_name="test_input",
            source_kind=SourceKind.EXTERNAL,
            session_key=session_key,
            actor=Actor(
                actor_id="test_user",
                actor_type="user",
                display_name="Test User"
            ),
            payload=MessagePayload(text="我刚才问了什么？"),
        )
        
        payload_text_2 = msg2.payload.text if isinstance(msg2.payload, MessagePayload) else "unknown"
        logger.info(f"Publishing message 2: {payload_text_2}")
        core.bus.publish_nowait(msg2)
        
        # 等待 Agent 处理第二条消息（用 polling）
        max_wait_seconds = 5.0
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < max_wait_seconds:
            state = core.get_state(session_key)
            final_agent_replies = [obs for obs in state.recent_obs if obs.source_name.startswith("agent")]
            if len(final_agent_replies) >= 2:
                break
            await asyncio.sleep(0.1)
        assert len(final_agent_replies) >= 2, (
            f"Should have at least 2 agent replies, got {len(final_agent_replies)}"
        )
        
        logger.info(f"✓ Context-aware E2E test passed ✓")
    
    finally:
        run_task.cancel()
        try:
            await asyncio.gather(run_task, return_exceptions=True)
        except Exception:
            pass
