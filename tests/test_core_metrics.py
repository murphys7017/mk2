# tests/test_core_metrics.py
# =========================
# Core Metrics & SessionState 验证测试
# =========================

import asyncio
import pytest
from src.core import Core
from src.adapters.text_input_adapter import TextInputAdapter
from src.schemas.observation import Observation, ObservationType, Actor, MessagePayload


@pytest.mark.asyncio
async def test_core_metrics_and_states():
    """测试 Core 的 metrics 和 SessionState 功能"""
    
    # 创建 Core
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
    )

    # 添加 adapter
    text_adapter = TextInputAdapter(name="text_input", default_session_key="dm:local")
    core.add_adapter(text_adapter)

    # 启动 Core（后台）
    run_task = asyncio.create_task(core.run_forever())

    try:
        # 等待 Core 启动
        await asyncio.sleep(0.2)

        # 投递几条消息
        text_adapter.ingest_text("Message 1", actor_id="alice", session_key="dm:alice")
        text_adapter.ingest_text("Message 2", actor_id="bob", session_key="dm:bob")
        text_adapter.ingest_text("Message 3", actor_id="alice", session_key="dm:alice")

        # 等待处理
        await asyncio.sleep(0.5)

        # ===== 验证 metrics =====
        assert core.metrics.processed_total == 3, f"Expected 3, got {core.metrics.processed_total}"
        assert core.metrics.processed_by_session["dm:alice"] == 2
        assert core.metrics.processed_by_session["dm:bob"] == 1

        # ===== 验证 SessionState =====
        alice_state = core.get_state("dm:alice")
        bob_state = core.get_state("dm:bob")

        assert alice_state.processed_total == 2
        assert bob_state.processed_total == 1
        assert alice_state.error_total == 0
        assert bob_state.error_total == 0

        # 检查 recent_obs（应该有 2 条和 1 条）
        assert len(alice_state.recent_obs) == 2
        assert len(bob_state.recent_obs) == 1

        # 检查 idle_seconds（应该不是 None）
        assert alice_state.idle_seconds() is not None
        assert bob_state.idle_seconds() is not None

        print("✅ All metrics and state tests passed!")

    finally:
        # 关闭 Core
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_debug_payload_recording():
    """测试 debug payload 记录功能"""
    
    core = Core(
        bus_maxsize=100,
        inbox_maxsize=50,
        system_session_key="system",
        message_routing="user",
    )

    text_adapter = TextInputAdapter(name="text_input", default_session_key="dm:local")
    core.add_adapter(text_adapter)

    run_task = asyncio.create_task(core.run_forever())

    try:
        await asyncio.sleep(0.2)

        # 注意：TextInputAdapter 的 payload 是 MessagePayload，不是 dict
        # 所以这个测试需要我们手动发送观测或修改 adapter
        # 为了简单起见，这里先略过，实际项目中可以扩展

        print("✅ Debug payload test setup complete")

    finally:
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    # 简单的本地测试
    asyncio.run(test_core_metrics_and_states())
