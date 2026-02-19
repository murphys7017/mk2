# Memory 子系统使用指南

## 概述

Memory 子系统提供了事件存储、对话轮次管理和记忆条目管理的完整接口骨架。

## 目录结构

```
src/memory/
  __init__.py       # 模块导出
  models.py         # 数据模型（已实现序列化/反序列化）
  stores.py         # 存储协议接口（Protocol）
  backend.py        # 后端协议接口（Protocol）
  service.py        # 服务层接口（方法签名）
```

## 核心模型

### 1. EventRecord - 事件记录

存储原始的 Observation 事件。

**字段：**
- `event_id: str` - 事件唯一标识
- `ts: float` - 时间戳
- `session_key: str` - 会话键
- `obs: Observation` - 观察对象
- `gate: dict | None` - Gate 处理结果
- `meta: dict` - 元数据
- `schema_version: int` - 模式版本

**序列化示例：**
```python
from src.schemas.observation import make_message_observation
from src.memory.models import EventRecord
import time

# 创建事件记录
obs = make_message_observation(
    source_name="cli",
    session_key="session_001",
    actor_id="user_123",
    text="Hello!"
)

event = EventRecord(
    event_id="evt_001",
    ts=time.time(),
    session_key="session_001",
    obs=obs,
)

# 序列化
event_dict = event.to_dict()
event_json = event.to_json()

# 反序列化
restored = EventRecord.from_dict(event_dict)
restored = EventRecord.from_json(event_json)
```

### 2. TurnRecord - 对话轮次记录

记录一个完整的对话轮次（输入 -> 计划 -> 执行 -> 输出）。

**字段：**
- `turn_id: str` - 轮次唯一标识
- `session_key: str` - 会话键
- `input_event_id: str` - 输入事件 ID
- `plan: dict | None` - 计划
- `tool_calls: list[dict]` - 工具调用列表
- `tool_results: list[dict]` - 工具结果列表
- `final_output_obs_id: str | None` - 最终输出观察 ID
- `started_ts: float | None` - 开始时间戳
- `finished_ts: float | None` - 结束时间戳
- `status: str` - 状态（ok / error / timeout）
- `error: str | None` - 错误信息
- `meta: dict` - 元数据
- `schema_version: int` - 模式版本

**使用示例：**
```python
from src.memory.models import TurnRecord
import time

turn = TurnRecord(
    turn_id="turn_001",
    session_key="session_001",
    input_event_id="evt_001",
    plan={"steps": ["analyze", "respond"]},
    started_ts=time.time(),
)

# 添加工具调用
turn.tool_calls.append({"tool": "search", "args": {"query": "test"}})
turn.tool_results.append({"result": "found"})

# 序列化
turn_json = turn.to_json()
```

### 3. MemoryItem - 记忆条目

存储结构化的记忆信息。

**字段：**
- `scope: str` - 作用域（persona / user / session / episodic / global）
- `kind: str` - 类型（fact / preference / goal / constraint ...）
- `key: str` - 唯一标识
- `content: str` - 文本描述
- `data: dict` - 结构化数据
- `source: str` - 来源
- `confidence: float` - 可信度 [0, 1]
- `created_ts: float | None` - 创建时间戳
- `updated_ts: float | None` - 更新时间戳
- `ttl_sec: int | None` - 生存时间（秒）
- `meta: dict` - 元数据
- `schema_version: int` - 模式版本

**使用示例：**
```python
from src.memory.models import MemoryItem
import time

item = MemoryItem(
    scope="persona",
    kind="fact",
    key="name",
    content="My name is Alice",
    data={"full_name": "Alice Smith"},
    source="user_input",
    confidence=0.95,
    created_ts=time.time(),
    ttl_sec=3600,  # 1小时后过期
)

# 检查是否过期
if item.is_expired():
    print("Memory item has expired")

# 序列化
item_dict = item.to_dict()
```

### 4. ContextPack - 上下文包

打包的上下文信息，提供给 Agent 使用。

**字段：**
- `persona: list[MemoryItem]` - Persona 记忆
- `user_profile: list[MemoryItem]` - 用户画像记忆
- `session_items: list[MemoryItem]` - 会话级记忆
- `episodic_items: list[MemoryItem]` - 情景记忆
- `recent_events: list[EventRecord]` - 最近事件
- `recent_turns: list[TurnRecord]` - 最近对话轮次
- `schema_version: int` - 模式版本

**使用示例：**
```python
from src.memory.models import ContextPack, MemoryItem, EventRecord, TurnRecord

pack = ContextPack(
    persona=[
        MemoryItem(scope="persona", kind="fact", key="name", content="Alice")
    ],
    recent_events=[event],
    recent_turns=[turn],
)

# 统计
print(f"Total memory items: {pack.total_items_count()}")
print(f"Total events/turns: {pack.total_events_count()}")

# 序列化
pack_json = pack.to_json(indent=2)
```

## 序列化机制

所有模型类都继承了 `SerializableMixin`，提供以下能力：

### 序列化

```python
# 转为 dict
data_dict = obj.to_dict()

# 转为 JSON
json_str = obj.to_json()
json_str = obj.to_json(indent=2)  # 格式化输出
```

### 反序列化

```python
# 从 dict 还原
obj = EventRecord.from_dict(data_dict)

# 从 JSON 还原
obj = EventRecord.from_json(json_str)
```

### Observation 序列化处理

系统自动处理 `Observation` 对象的序列化/反序列化：

**序列化时：**
- 优先使用 `model_dump()`（Pydantic v2）
- 其次使用 `dict()`（Pydantic v1）
- 再次使用 `to_dict()`（自定义）
- 然后使用 `dataclasses.asdict()`（dataclass）
- 最后使用 `vars()`（通用对象）

**反序列化时：**
- 优先使用 `model_validate()`（Pydantic v2）
- 其次使用 `parse_obj()`（Pydantic v1）
- 最后使用构造函数（dataclass）

## 存储协议

### EventStore

事件存储协议，定义了事件记录的 CRUD 操作：

```python
from src.memory.stores import EventStore

# Protocol 定义的方法：
# - save_event(event: EventRecord)
# - get_event(event_id: str) -> EventRecord | None
# - list_events_by_session(session_key, limit, offset, ...)
# - list_events_by_time_range(session_key, start_ts, end_ts, ...)
# - delete_events_by_session(session_key) -> int
# - count_events_by_session(session_key) -> int
```

### TurnStore

对话轮次存储协议：

```python
from src.memory.stores import TurnStore

# Protocol 定义的方法：
# - save_turn(turn: TurnRecord)
# - get_turn(turn_id: str) -> TurnRecord | None
# - list_turns_by_session(session_key, limit, offset, ...)
# - update_turn_status(turn_id, status, error)
# - delete_turns_by_session(session_key) -> int
# - count_turns_by_session(session_key) -> int
```

### MemoryStore

记忆条目存储协议：

```python
from src.memory.stores import MemoryStore

# Protocol 定义的方法：
# - save_memory(item: MemoryItem)
# - get_memory(scope, kind, key) -> MemoryItem | None
# - list_memories_by_scope(scope, kind, limit)
# - update_memory(scope, kind, key, content, data, confidence)
# - delete_memory(scope, kind, key) -> bool
# - delete_memories_by_scope(scope, kind) -> int
# - search_memories(query, scope, kind, limit)
# - cleanup_expired_memories(now_ts) -> int
```

## 后端协议

### StorageBackend

底层存储后端协议，支持多种实现（SQLite / JSONL / InMemory / Redis）：

```python
from src.memory.backend import StorageBackend

# Protocol 定义的方法：
# - initialize()
# - close()
# - insert(collection, data)
# - get(collection, key) -> dict | None
# - update(collection, key, data) -> bool
# - delete(collection, key) -> bool
# - query(collection, filters, order_by, limit, offset)
# - count(collection, filters) -> int
# - delete_many(collection, filters) -> int
# - search_text(collection, text_field, query, ...)
# - query_range(collection, range_field, start, end, ...)
# - health_check() -> dict
```

## 服务层

### MemoryService

高层次的记忆管理服务（方法签名已定义，实现待补充）：

```python
from src.memory.service import MemoryService

# 初始化服务
service = MemoryService(
    event_store=my_event_store,
    turn_store=my_turn_store,
    memory_store=my_memory_store,
)

# 事件管理
# await service.record_event(obs, gate_result, meta)
# await service.get_event(event_id)
# await service.get_recent_events(session_key, limit)

# 对话轮次管理
# await service.start_turn(session_key, input_event_id, plan)
# await service.finish_turn(turn_id, final_output_obs_id, status, error)
# await service.add_tool_call_to_turn(turn_id, tool_call, tool_result)

# 记忆条目管理
# await service.save_memory(scope, kind, key, content, ...)
# await service.get_memory(scope, kind, key)
# await service.search_memories(query, scope, kind, limit)

# 上下文构建
# pack = await service.build_context_pack(session_key, ...)
# pack = await service.build_lightweight_context(session_key, ...)

# 会话管理
# summary = await service.get_session_summary(session_key)
# result = await service.clear_session(session_key, ...)
# archive = await service.archive_session(session_key)
# session_key = await service.restore_session(archive_data)
```

## 下一步工作

1. **实现具体的 Backend**
   - SQLiteBackend（持久化存储）
   - InMemoryBackend（测试/临时存储）
   - JSONLBackend（日志式存储）

2. **实现具体的 Store**
   - EventStoreImpl
   - TurnStoreImpl
   - MemoryStoreImpl

3. **完善 MemoryService 实现**
   - 实现所有方法体
   - 添加事务支持
   - 添加错误处理

4. **扩展功能**
   - 记忆检索与召回（RAG）
   - 记忆压缩与归档
   - 记忆重要性评估
   - 跨会话记忆迁移

## 测试

运行序列化测试：

```bash
python test_memory_serialization.py
```

测试内容：
- EventRecord 序列化/反序列化
- TurnRecord 序列化/反序列化
- MemoryItem 序列化/反序列化（含过期检查）
- ContextPack 序列化/反序列化

所有测试均通过 ✓
