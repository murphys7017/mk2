#!/usr/bin/env python3
# test_memory_serialization.py
# 测试 memory 子系统的序列化/反序列化功能

from __future__ import annotations

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.schemas.observation import make_message_observation
from src.memory.models import EventRecord, TurnRecord, MemoryItem, ContextPack


def test_event_record_serialization():
    """测试 EventRecord 序列化/反序列化"""
    print("=" * 60)
    print("测试 EventRecord 序列化/反序列化")
    print("=" * 60)
    
    # 创建一个 Observation
    obs = make_message_observation(
        source_name="test_cli",
        session_key="test_session_001",
        actor_id="user_123",
        text="Hello, world!",
        metadata={"test": True},
    )
    
    # 创建 EventRecord
    event = EventRecord(
        event_id="evt_001",
        ts=time.time(),
        session_key="test_session_001",
        obs=obs,
        gate={"allowed": True, "reason": "normal"},
        meta={"source": "test"},
    )
    
    print(f"原始 EventRecord:")
    print(f"  event_id: {event.event_id}")
    print(f"  session_key: {event.session_key}")
    print(f"  obs.obs_id: {event.obs.obs_id}")
    print(f"  obs.obs_type: {event.obs.obs_type}")
    
    # 序列化为 dict
    event_dict = event.to_dict()
    print(f"\n序列化为 dict:")
    print(f"  event_id: {event_dict['event_id']}")
    print(f"  obs.obs_id: {event_dict['obs']['obs_id']}")
    print(f"  obs.obs_type: {event_dict['obs']['obs_type']}")
    
    # 序列化为 JSON
    event_json = event.to_json(indent=2)
    print(f"\n序列化为 JSON (前 200 字符):")
    print(event_json[:200] + "...")
    
    # 从 dict 反序列化
    event_restored = EventRecord.from_dict(event_dict)
    print(f"\n从 dict 反序列化:")
    print(f"  event_id: {event_restored.event_id}")
    print(f"  session_key: {event_restored.session_key}")
    print(f"  obs.obs_id: {event_restored.obs.obs_id}")
    print(f"  obs.obs_type: {event_restored.obs.obs_type}")
    
    # 从 JSON 反序列化
    event_from_json = EventRecord.from_json(event_json)
    print(f"\n从 JSON 反序列化:")
    print(f"  event_id: {event_from_json.event_id}")
    print(f"  session_key: {event_from_json.session_key}")
    print(f"  obs.obs_id: {event_from_json.obs.obs_id}")
    
    print("\n✓ EventRecord 序列化/反序列化测试通过!")
    return True


def test_turn_record_serialization():
    """测试 TurnRecord 序列化/反序列化"""
    print("\n" + "=" * 60)
    print("测试 TurnRecord 序列化/反序列化")
    print("=" * 60)
    
    # 创建 TurnRecord
    turn = TurnRecord(
        turn_id="turn_001",
        session_key="test_session_001",
        input_event_id="evt_001",
        plan={"steps": ["analyze", "respond"]},
        tool_calls=[{"tool": "search", "args": {"query": "test"}}],
        tool_results=[{"result": "found"}],
        final_output_obs_id="evt_002",
        started_ts=time.time(),
        finished_ts=time.time() + 1.5,
        status="ok",
    )
    
    print(f"原始 TurnRecord:")
    print(f"  turn_id: {turn.turn_id}")
    print(f"  status: {turn.status}")
    print(f"  tool_calls: {len(turn.tool_calls)}")
    
    # 序列化与反序列化
    turn_dict = turn.to_dict()
    turn_json = turn.to_json()
    turn_restored = TurnRecord.from_dict(turn_dict)
    
    print(f"\n反序列化后:")
    print(f"  turn_id: {turn_restored.turn_id}")
    print(f"  status: {turn_restored.status}")
    print(f"  tool_calls: {len(turn_restored.tool_calls)}")
    
    print("\n✓ TurnRecord 序列化/反序列化测试通过!")
    return True


def test_memory_item_serialization():
    """测试 MemoryItem 序列化/反序列化"""
    print("\n" + "=" * 60)
    print("测试 MemoryItem 序列化/反序列化")
    print("=" * 60)
    
    # 创建 MemoryItem
    item = MemoryItem(
        scope="persona",
        kind="fact",
        key="name",
        content="My name is Alice",
        data={"full_name": "Alice Smith"},
        source="user_input",
        confidence=0.95,
        created_ts=time.time(),
        ttl_sec=3600,
    )
    
    print(f"原始 MemoryItem:")
    print(f"  scope: {item.scope}, kind: {item.kind}, key: {item.key}")
    print(f"  content: {item.content}")
    print(f"  confidence: {item.confidence}")
    
    # 序列化与反序列化
    item_dict = item.to_dict()
    item_json = item.to_json()
    item_restored = MemoryItem.from_dict(item_dict)
    
    print(f"\n反序列化后:")
    print(f"  scope: {item_restored.scope}, kind: {item_restored.kind}")
    print(f"  content: {item_restored.content}")
    print(f"  confidence: {item_restored.confidence}")
    
    # 测试过期检查
    print(f"\n过期检查:")
    print(f"  is_expired (当前时间): {item.is_expired()}")
    print(f"  is_expired (1小时后): {item.is_expired(item.created_ts + 3601)}")
    
    print("\n✓ MemoryItem 序列化/反序列化测试通过!")
    return True


def test_context_pack_serialization():
    """测试 ContextPack 序列化/反序列化"""
    print("\n" + "=" * 60)
    print("测试 ContextPack 序列化/反序列化")
    print("=" * 60)
    
    # 创建一些测试数据
    obs = make_message_observation(
        source_name="test_cli",
        session_key="test_session_001",
        actor_id="user_123",
        text="Test message",
    )
    
    event = EventRecord(
        event_id="evt_001",
        ts=time.time(),
        session_key="test_session_001",
        obs=obs,
    )
    
    turn = TurnRecord(
        turn_id="turn_001",
        session_key="test_session_001",
        input_event_id="evt_001",
    )
    
    item = MemoryItem(
        scope="persona",
        kind="fact",
        key="name",
        content="Alice",
    )
    
    # 创建 ContextPack
    pack = ContextPack(
        persona=[item],
        user_profile=[],
        session_items=[],
        episodic_items=[],
        recent_events=[event],
        recent_turns=[turn],
    )
    
    print(f"原始 ContextPack:")
    print(f"  persona: {pack.total_items_count()} items")
    print(f"  events/turns: {pack.total_events_count()} records")
    
    # 序列化与反序列化
    pack_dict = pack.to_dict()
    pack_json = pack.to_json()
    pack_restored = ContextPack.from_dict(pack_dict)
    
    print(f"\n反序列化后:")
    print(f"  persona: {pack_restored.total_items_count()} items")
    print(f"  events/turns: {pack_restored.total_events_count()} records")
    print(f"  recent_events[0].event_id: {pack_restored.recent_events[0].event_id}")
    print(f"  recent_turns[0].turn_id: {pack_restored.recent_turns[0].turn_id}")
    
    print("\n✓ ContextPack 序列化/反序列化测试通过!")
    return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Memory 子系统序列化/反序列化测试")
    print("=" * 60 + "\n")
    
    tests = [
        test_event_record_serialization,
        test_turn_record_serialization,
        test_memory_item_serialization,
        test_context_pack_serialization,
    ]
    
    results = []
    for test_func in tests:
        try:
            results.append(test_func())
        except Exception as e:
            print(f"\n✗ 测试失败: {test_func.__name__}")
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"通过: {sum(results)}/{len(results)}")
    print(f"失败: {len(results) - sum(results)}/{len(results)}")
    
    if all(results):
        print("\n✓ 所有测试通过!")
        return 0
    else:
        print("\n✗ 部分测试失败!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
