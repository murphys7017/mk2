# memory/models.py
# =========================
# 记忆子系统数据模型（Memory Subsystem Models）
# 支持序列化/反序列化，包括对 Observation 的兼容处理
# =========================

from __future__ import annotations

import json
import time
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from src.schemas.observation import Observation


# =============================================================================
# 序列化工具函数 / Serialization Utilities
# =============================================================================

def _serialize_value(value: Any) -> Any:
    """
    递归序列化值，处理常见类型
    Recursively serialize value, handling common types
    """
    # None, bool, int, float, str 直接返回
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    
    # datetime 转 ISO 格式
    if isinstance(value, datetime):
        return value.isoformat()
    
    # Enum 转字符串值
    if isinstance(value, Enum):
        return value.value
    
    # set 转列表
    if isinstance(value, set):
        return [_serialize_value(item) for item in value]
    
    # list 递归处理
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    
    # dict 递归处理
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    
    # pydantic v2 model
    if hasattr(value, "model_dump"):
        return value.model_dump()
    
    # pydantic v1 model
    if hasattr(value, "dict"):
        return value.dict()
    
    # dataclass
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # 使用 dataclasses.asdict 然后递归序列化
        return _serialize_value(dataclasses.asdict(value))
    
    # 自定义 to_dict
    if hasattr(value, "to_dict"):
        return value.to_dict()
    
    # 最后尝试 vars()
    try:
        return vars(value)
    except TypeError:
        # 如果都不行，转为字符串
        return str(value)


def _deserialize_observation(data: dict) -> Observation:
    """
    从 dict 还原 Observation 对象
    Deserialize Observation from dict
    
    兼容 pydantic v1/v2 和 dataclass
    Compatible with pydantic v1/v2 and dataclass
    """
    from src.schemas.observation import (
        Observation,
        ObservationType,
        SourceKind,
        Actor,
        EvidenceRef,
        MessagePayload,
        WorldDataPayload,
        AlertPayload,
        ControlPayload,
        SchedulePayload,
    )
    
    # 处理枚举类型
    if "obs_type" in data and isinstance(data["obs_type"], str):
        data["obs_type"] = ObservationType(data["obs_type"])
    if "source_kind" in data and isinstance(data["source_kind"], str):
        data["source_kind"] = SourceKind(data["source_kind"])
    
    # 处理 datetime
    for dt_field in ["timestamp", "received_at"]:
        if dt_field in data and isinstance(data[dt_field], str):
            data[dt_field] = datetime.fromisoformat(data[dt_field])
    
    # 处理 actor
    if "actor" in data and isinstance(data["actor"], dict):
        data["actor"] = Actor(**data["actor"])
    
    # 处理 evidence
    if "evidence" in data and isinstance(data["evidence"], dict):
        data["evidence"] = EvidenceRef(**data["evidence"])
    
    # 处理 payload（根据 obs_type）
    if "payload" in data and isinstance(data["payload"], dict):
        payload_data = data["payload"]
        obs_type = data.get("obs_type", ObservationType.MESSAGE)
        
        if obs_type == ObservationType.MESSAGE:
            # 处理 attachments
            from src.schemas.observation import AttachmentRef
            if "attachments" in payload_data:
                payload_data["attachments"] = [
                    AttachmentRef(**att) if isinstance(att, dict) else att
                    for att in payload_data["attachments"]
                ]
            data["payload"] = MessagePayload(**payload_data)
        elif obs_type == ObservationType.WORLD_DATA:
            data["payload"] = WorldDataPayload(**payload_data)
        elif obs_type == ObservationType.ALERT:
            data["payload"] = AlertPayload(**payload_data)
        elif obs_type == ObservationType.CONTROL:
            data["payload"] = ControlPayload(**payload_data)
        elif obs_type == ObservationType.SCHEDULE:
            data["payload"] = SchedulePayload(**payload_data)
    
    # 处理 quality_flags (set)
    if "quality_flags" in data:
        if isinstance(data["quality_flags"], list):
            data["quality_flags"] = set(data["quality_flags"])
    
    # 处理 tags (set)
    if "tags" in data:
        if isinstance(data["tags"], list):
            data["tags"] = set(data["tags"])
    
    # pydantic v2
    if hasattr(Observation, "model_validate"):
        return Observation.model_validate(data)
    # pydantic v1
    elif hasattr(Observation, "parse_obj"):
        return Observation.parse_obj(data)
    # dataclass（当前实现）
    else:
        return Observation(**data)


# =============================================================================
# SerializableMixin
# =============================================================================

class SerializableMixin:
    """
    序列化/反序列化能力混入类
    Mixin for serialization/deserialization capabilities
    
    提供：
    - to_dict() -> dict
    - to_json() -> str
    - from_dict(data: dict) -> Self
    - from_json(s: str) -> Self
    """
    
    def to_dict(self) -> dict:
        """
        转换为 dict
        Convert to dict
        """
        if not dataclasses.is_dataclass(self):
            raise TypeError(f"{self.__class__.__name__} 必须是 dataclass")
        
        # 获取所有字段
        result = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            result[f.name] = _serialize_value(value)
        
        return result
    
    def to_json(self, ensure_ascii: bool = False, indent: int | None = None) -> str:
        """
        转换为 JSON 字符串
        Convert to JSON string
        """
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, indent=indent)
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """
        从 dict 还原对象
        Restore object from dict
        """
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f"{cls.__name__} 必须是 dataclass")
        
        # 创建副本避免修改原数据
        data = dict(data)
        
        # 获取字段类型信息
        field_types = {f.name: f.type for f in dataclasses.fields(cls)}
        
        # 处理特殊字段
        # 子类可以重写 _deserialize_field 方法来自定义反序列化逻辑
        if hasattr(cls, "_deserialize_field"):
            for field_name, field_type in field_types.items():
                if field_name in data:
                    data[field_name] = cls._deserialize_field(field_name, data[field_name], field_type)
        
        return cls(**data)
    
    @classmethod
    def from_json(cls, s: str) -> Self:
        """
        从 JSON 字符串还原对象
        Restore object from JSON string
        """
        data = json.loads(s)
        return cls.from_dict(data)


# =============================================================================
# EventRecord - 事件记录
# =============================================================================

@dataclass
class EventRecord(SerializableMixin):
    """
    事件记录（Event Record）
    
    存储原始的 Observation 事件
    Store raw Observation events
    """
    event_id: str
    ts: float
    session_key: str
    obs: Observation
    gate: dict | None = None
    meta: dict = field(default_factory=dict)
    schema_version: int = 1
    
    @classmethod
    def _deserialize_field(cls, field_name: str, value: Any, field_type: Any) -> Any:
        """
        自定义字段反序列化逻辑
        Custom field deserialization logic
        """
        # 处理 Observation
        if field_name == "obs" and isinstance(value, dict):
            return _deserialize_observation(value)
        return value


# =============================================================================
# TurnRecord - 对话轮次记录
# =============================================================================

@dataclass
class TurnRecord(SerializableMixin):
    """
    对话轮次记录（Turn Record）
    
    记录一个完整的对话轮次（输入 -> 计划 -> 执行 -> 输出）
    Record a complete conversation turn (input -> plan -> execute -> output)
    """
    turn_id: str
    session_key: str
    input_event_id: str
    plan: dict | None = None
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    final_output_obs_id: str | None = None
    started_ts: float | None = None
    finished_ts: float | None = None
    status: str = "ok"
    error: str | None = None
    meta: dict = field(default_factory=dict)
    schema_version: int = 1


# =============================================================================
# MemoryItem - 记忆条目
# =============================================================================

@dataclass
class MemoryItem(SerializableMixin):
    """
    记忆条目（Memory Item）
    
    存储结构化的记忆信息（persona, user_profile, session, episodic 等）
    Store structured memory information
    """
    scope: str          # persona / user / session / episodic / global
    kind: str           # fact / preference / goal / constraint / note ...
    key: str            # 唯一标识 / unique identifier
    content: str        # 文本描述 / text description
    data: dict = field(default_factory=dict)          # 结构化数据
    source: str = "unknown"                           # 来源
    confidence: float = 1.0                           # 可信度 [0, 1]
    created_ts: float | None = None                   # 创建时间
    updated_ts: float | None = None                   # 更新时间
    ttl_sec: int | None = None                        # 生存时间（秒）
    meta: dict = field(default_factory=dict)
    schema_version: int = 1
    
    def is_expired(self, now_ts: float | None = None) -> bool:
        """
        检查是否过期
        Check if expired
        """
        if self.ttl_sec is None:
            return False
        if self.created_ts is None:
            return False
        if now_ts is None:
            now_ts = time.time()
        return (now_ts - self.created_ts) > self.ttl_sec


# =============================================================================
# ContextPack - 上下文包
# =============================================================================

@dataclass
class ContextPack(SerializableMixin):
    """
    上下文包（Context Pack）
    
    打包的上下文信息，提供给 Agent 使用
    Packaged context information for Agent
    """
    persona: list[MemoryItem] = field(default_factory=list)
    user_profile: list[MemoryItem] = field(default_factory=list)
    session_items: list[MemoryItem] = field(default_factory=list)
    episodic_items: list[MemoryItem] = field(default_factory=list)
    recent_events: list[EventRecord] = field(default_factory=list)
    recent_turns: list[TurnRecord] = field(default_factory=list)
    schema_version: int = 1
    
    @classmethod
    def _deserialize_field(cls, field_name: str, value: Any, field_type: Any) -> Any:
        """
        自定义字段反序列化逻辑
        Custom field deserialization logic
        """
        # 处理 MemoryItem 列表
        if field_name in ("persona", "user_profile", "session_items", "episodic_items"):
            if isinstance(value, list):
                return [
                    MemoryItem.from_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
        
        # 处理 EventRecord 列表
        if field_name == "recent_events":
            if isinstance(value, list):
                return [
                    EventRecord.from_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
        
        # 处理 TurnRecord 列表
        if field_name == "recent_turns":
            if isinstance(value, list):
                return [
                    TurnRecord.from_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
        
        return value
    
    def total_items_count(self) -> int:
        """
        统计总记忆条目数
        Count total memory items
        """
        return (
            len(self.persona)
            + len(self.user_profile)
            + len(self.session_items)
            + len(self.episodic_items)
        )
    
    def total_events_count(self) -> int:
        """
        统计总事件数
        Count total events
        """
        return len(self.recent_events) + len(self.recent_turns)
