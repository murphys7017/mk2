#!/usr/bin/env python3
# examples/memory_usage_example.py
# Memory 子系统使用示例

"""
本示例展示如何使用 Memory 子系统的核心功能：
1. 创建和序列化事件记录
2. 管理对话轮次
3. 存储和检索记忆条目
4. 构建上下文包
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.schemas.observation import make_message_observation
from src.memory.models import EventRecord, TurnRecord, MemoryItem, ContextPack


def example_1_event_record():
    """示例 1: 创建和序列化事件记录"""
    print("=" * 70)
    print("示例 1: 创建和序列化事件记录")
    print("=" * 70)
    
    # 1. 创建一个 Observation
    obs = make_message_observation(
        source_name="web_chat",
        session_key="session_alice_001",
        actor_id="alice",
        text="你好，我想了解今天的天气",
        metadata={"channel": "web", "ip": "192.168.1.100"}
    )
    
    # 2. 创建 EventRecord
    event = EventRecord(
        event_id="evt_20260214_001",
        ts=time.time(),
        session_key="session_alice_001",
        obs=obs,
        gate={"allowed": True, "reason": "normal", "confidence": 1.0},
        meta={"adapter": "web_chat_adapter", "version": "1.0"}
    )
    
    print(f"\n创建的事件记录:")
    print(f"  Event ID: {event.event_id}")
    print(f"  Session: {event.session_key}")
    print(f"  User Message: {obs.payload.text}")
    print(f"  Timestamp: {event.ts}")
    
    # 3. 序列化为 JSON（用于存储或传输）
    event_json = event.to_json(indent=2)
    print(f"\n序列化为 JSON（前 300 字符）:")
    print(event_json[:300] + "...")
    
    # 4. 从 JSON 反序列化（模拟从存储加载）
    loaded_event = EventRecord.from_json(event_json)
    print(f"\n从 JSON 加载的事件:")
    print(f"  Event ID: {loaded_event.event_id}")
    print(f"  User Message: {loaded_event.obs.payload.text}")
    
    return event


def example_2_turn_record(input_event: EventRecord):
    """示例 2: 管理对话轮次"""
    print("\n" + "=" * 70)
    print("示例 2: 管理对话轮次")
    print("=" * 70)
    
    # 1. 开始一个对话轮次
    turn = TurnRecord(
        turn_id="turn_20260214_001",
        session_key=input_event.session_key,
        input_event_id=input_event.event_id,
        plan={
            "intent": "weather_query",
            "steps": ["get_location", "fetch_weather", "format_response"]
        },
        started_ts=time.time(),
    )
    
    print(f"\n开始对话轮次:")
    print(f"  Turn ID: {turn.turn_id}")
    print(f"  Input Event: {turn.input_event_id}")
    print(f"  Plan Steps: {turn.plan['steps']}")
    
    # 2. 记录工具调用
    turn.tool_calls.append({
        "tool": "get_location",
        "args": {"user_id": "alice"},
        "timestamp": time.time(),
    })
    
    turn.tool_results.append({
        "tool": "get_location",
        "result": {"city": "北京", "district": "朝阳区"},
        "success": True,
    })
    
    turn.tool_calls.append({
        "tool": "fetch_weather",
        "args": {"city": "北京"},
        "timestamp": time.time(),
    })
    
    turn.tool_results.append({
        "tool": "fetch_weather",
        "result": {
            "temperature": 15,
            "weather": "晴天",
            "aqi": 45
        },
        "success": True,
    })
    
    print(f"\n工具调用记录:")
    for i, (call, result) in enumerate(zip(turn.tool_calls, turn.tool_results), 1):
        print(f"  {i}. {call['tool']}: {result['success']}")
    
    # 3. 完成轮次
    turn.finished_ts = time.time()
    turn.status = "ok"
    turn.final_output_obs_id = "evt_20260214_002"
    
    print(f"\n对话轮次完成:")
    print(f"  Status: {turn.status}")
    print(f"  Duration: {turn.finished_ts - turn.started_ts:.3f}s")
    
    # 4. 序列化
    turn_json = turn.to_json(indent=2)
    print(f"\n轮次记录已序列化（{len(turn_json)} 字符）")
    
    return turn


def example_3_memory_items():
    """示例 3: 存储和检索记忆条目"""
    print("\n" + "=" * 70)
    print("示例 3: 存储和检索记忆条目")
    print("=" * 70)
    
    memories = []
    
    # 1. Persona 记忆（系统人格）
    persona_memory = MemoryItem(
        scope="persona",
        kind="fact",
        key="assistant_role",
        content="我是一个友好、专业的 AI 助手，擅长提供准确的信息",
        data={"role": "assistant", "tone": "friendly", "expertise": ["weather", "general_qa"]},
        source="system_config",
        confidence=1.0,
        created_ts=time.time(),
    )
    memories.append(persona_memory)
    print(f"\nPersona 记忆:")
    print(f"  {persona_memory.content}")
    
    # 2. User Profile 记忆（用户画像）
    user_profile = MemoryItem(
        scope="user",
        kind="preference",
        key="alice_location",
        content="用户 Alice 位于北京朝阳区",
        data={"user_id": "alice", "city": "北京", "district": "朝阳区"},
        source="location_service",
        confidence=0.95,
        created_ts=time.time(),
    )
    memories.append(user_profile)
    print(f"\nUser Profile 记忆:")
    print(f"  {user_profile.content}")
    
    # 3. Session 记忆（会话级）
    session_memory = MemoryItem(
        scope="session",
        kind="context",
        key="current_topic",
        content="当前对话主题：天气查询",
        data={"topic": "weather", "subtopic": "current_weather"},
        source="dialogue_analysis",
        confidence=0.9,
        created_ts=time.time(),
        ttl_sec=3600,  # 1小时后过期
    )
    memories.append(session_memory)
    print(f"\nSession 记忆:")
    print(f"  {session_memory.content}")
    print(f"  过期时间: {session_memory.ttl_sec}秒后")
    
    # 4. Episodic 记忆（情景记忆）
    episodic_memory = MemoryItem(
        scope="episodic",
        kind="fact",
        key="weather_beijing_20260214",
        content="2026年2月14日北京天气：15度，晴天，AQI 45",
        data={"date": "2026-02-14", "city": "北京", "temp": 15, "weather": "晴天", "aqi": 45},
        source="weather_api",
        confidence=0.98,
        created_ts=time.time(),
        ttl_sec=86400,  # 24小时后过期
    )
    memories.append(episodic_memory)
    print(f"\nEpisodic 记忆:")
    print(f"  {episodic_memory.content}")
    
    # 5. 序列化所有记忆
    print(f"\n序列化 {len(memories)} 条记忆:")
    for mem in memories:
        mem_dict = mem.to_dict()
        print(f"  - {mem.scope}/{mem.kind}/{mem.key}")
    
    return memories


def example_4_context_pack(event: EventRecord, turn: TurnRecord, memories: list[MemoryItem]):
    """示例 4: 构建上下文包"""
    print("\n" + "=" * 70)
    print("示例 4: 构建上下文包")
    print("=" * 70)
    
    # 1. 分类记忆条目
    persona = [m for m in memories if m.scope == "persona"]
    user_profile = [m for m in memories if m.scope == "user"]
    session_items = [m for m in memories if m.scope == "session"]
    episodic_items = [m for m in memories if m.scope == "episodic"]
    
    # 2. 构建上下文包
    context_pack = ContextPack(
        persona=persona,
        user_profile=user_profile,
        session_items=session_items,
        episodic_items=episodic_items,
        recent_events=[event],
        recent_turns=[turn],
    )
    
    print(f"\n上下文包统计:")
    print(f"  Persona 记忆: {len(context_pack.persona)} 条")
    print(f"  User Profile 记忆: {len(context_pack.user_profile)} 条")
    print(f"  Session 记忆: {len(context_pack.session_items)} 条")
    print(f"  Episodic 记忆: {len(context_pack.episodic_items)} 条")
    print(f"  总记忆条目: {context_pack.total_items_count()} 条")
    print(f"  最近事件: {len(context_pack.recent_events)} 条")
    print(f"  最近轮次: {len(context_pack.recent_turns)} 条")
    print(f"  总事件/轮次: {context_pack.total_events_count()} 条")
    
    # 3. 序列化上下文包
    pack_json = context_pack.to_json(indent=2)
    print(f"\n上下文包序列化:")
    print(f"  JSON 大小: {len(pack_json)} 字符")
    print(f"  前 200 字符: {pack_json[:200]}...")
    
    # 4. 反序列化验证
    restored_pack = ContextPack.from_json(pack_json)
    print(f"\n反序列化验证:")
    print(f"  总记忆条目: {restored_pack.total_items_count()} 条")
    print(f"  总事件/轮次: {restored_pack.total_events_count()} 条")
    print(f"  ✓ 序列化/反序列化成功!")
    
    return context_pack


def main():
    """运行所有示例"""
    print("\n" + "=" * 70)
    print("Memory 子系统使用示例")
    print("=" * 70 + "\n")
    
    # 运行示例
    event = example_1_event_record()
    turn = example_2_turn_record(event)
    memories = example_3_memory_items()
    context_pack = example_4_context_pack(event, turn, memories)
    
    # 总结
    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    print(f"✓ 成功示范了 Memory 子系统的核心功能:")
    print(f"  1. EventRecord - 事件记录的创建和序列化")
    print(f"  2. TurnRecord - 对话轮次的管理和追踪")
    print(f"  3. MemoryItem - 多层次记忆条目的存储")
    print(f"  4. ContextPack - 上下文包的构建和序列化")
    print(f"\n✓ 所有模型都支持完整的序列化/反序列化!")
    print(f"✓ Observation 对象的序列化得到正确处理!")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
