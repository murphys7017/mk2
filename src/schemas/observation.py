# observation.py
# =========================
# 观察事件模型（Observation）
# Observation = I observed something happened in the world
# =========================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
import uuid


# ============================================================
# 枚举定义 / Enum definitions
# ============================================================

class ObservationType(str, Enum):
    """
    观察类型：世界发生了什么
    Observation type: what kind of world event was observed
    """
    MESSAGE = "message"        # 有人说话 / Someone said something
    WORLD_DATA = "world_data"  # 世界数据（天气、指标等）/ External world data
    ALERT = "alert"            # 告警、异常 / Alert or anomaly
    SCHEDULE = "schedule"      # 定时事件 / Scheduled event
    SYSTEM = "system"          # 系统内部事件 / Internal system event


class SourceKind(str, Enum):
    """
    输入源类型（只用于观测，不用于业务决策）
    Source kind (for observability only, not for decisions)
    """
    EXTERNAL = "external"      # 外部世界 / External world
    INTERNAL = "internal"      # 系统自身 / Internal system


# 质量标记：用于提示输入质量，不直接做决策
# Quality flags: hints about input quality, not decisions
QualityFlag = Literal[
    "EMPTY_CONTENT",       # 内容为空 / Empty content
    "MISSING_IDENTITY",    # 缺少身份 / Missing actor identity
    "MISSING_SESSION",     # 缺少会话域 / Missing session key
    "SUSPECT_INJECTION",   # 疑似注入 / Suspected prompt injection
    "DUPLICATE",           # 重复事件 / Duplicate event
    "TRUNCATED",           # 内容被截断 / Truncated content
    "UNSUPPORTED",         # 不支持的事件 / Unsupported event
    "LOW_CONFIDENCE",      # 低可信度 / Low confidence
]


# ============================================================
# 证据 / 身份 / 附件
# Evidence / Actor / Attachment
# ============================================================

@dataclass(frozen=True)
class EvidenceRef:
    """
    原始证据引用（用于审计、回放、调试）
    Reference to raw/original evidence (audit / replay / debug)
    """
    raw_event_id: Optional[str] = None      # 原始事件ID（如 message_id）
    raw_event_uri: Optional[str] = None     # 原始数据存储位置（URI）
    signature: Optional[str] = None         # 签名（可选）
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Actor:
    """
    触发这个观察的主体
    Who caused this observation
    """
    actor_id: Optional[str] = None          # 用户ID / 系统ID
    actor_type: Literal["user", "system", "service", "unknown"] = "unknown"
    display_name: Optional[str] = None
    tenant_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttachmentRef:
    """
    附件引用（不包含二进制内容）
    Attachment reference (no raw bytes)
    """
    id: str
    kind: Literal["image", "file", "audio", "video", "unknown"] = "unknown"
    uri: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    text_hint: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Payload 定义（观察到的“内容”）
# Payload definitions (what was observed)
# ============================================================

@dataclass(frozen=True)
class MessagePayload:
    """
    对话类观察（有人说了什么）
    Message-like observation
    """
    text: Optional[str] = None
    attachments: List[AttachmentRef] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldDataPayload:
    """
    世界数据观察（结构化）
    Structured world data observation
    """
    schema_id: str                            # 数据结构标识
    data: Dict[str, Any]                     # 实际数据
    validity_seconds: Optional[int] = None   # 有效期
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AlertPayload:
    """
    告警 / 异常观察
    Alert or anomaly observation
    """
    alert_type: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    message: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SchedulePayload:
    """
    定时 / 计划事件
    Scheduled event
    """
    schedule_id: str
    data: Dict[str, Any] = field(default_factory=dict)


Payload = MessagePayload | WorldDataPayload | AlertPayload | SchedulePayload


# ============================================================
# Observation 核心定义
# Core Observation definition
# ============================================================

@dataclass
class Observation:
    """
    Observation = 我观察到了世界发生了什么
    Observation = I observed something happened in the world

    Adapter 的唯一输出
    The ONLY output of adapters
    """

    obs_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    obs_type: ObservationType = ObservationType.MESSAGE
    source_name: str = "unknown"              # 输入源名称（观测用）
    source_kind: SourceKind = SourceKind.EXTERNAL

    # 事件时间 & 系统接收时间
    # Event time & ingest time
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # 会话隔离域
    # Conversation isolation domain
    session_key: Optional[str] = None

    actor: Actor = field(default_factory=Actor)
    payload: Payload = field(default_factory=MessagePayload)
    evidence: EvidenceRef = field(default_factory=EvidenceRef)

    # 质量与辅助信息（不做决策）
    # Quality hints (not decisions)
    quality_flags: set[QualityFlag] = field(default_factory=set)
    confidence: Optional[float] = None
    tags: set[str] = field(default_factory=set)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """
        最小校验（Adapter 阶段）
        Minimal validation at adapter level
        """
        if not self.source_name:
            raise ValueError("source_name 不能为空 / source_name must not be empty")

        if self.timestamp.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("时间必须带时区 / datetime must be timezone-aware")

        if self.obs_type == ObservationType.MESSAGE:
            mp = self._as_message()
            if (not mp.text or mp.text.strip() == "") and not mp.attachments:
                self.quality_flags.add("EMPTY_CONTENT")
            if not self.session_key:
                self.quality_flags.add("MISSING_SESSION")
            if not self.actor.actor_id:
                self.quality_flags.add("MISSING_IDENTITY")

        if self.obs_type == ObservationType.WORLD_DATA:
            wp = self._as_world()
            if not wp.schema_id:
                raise ValueError("schema_id 不能为空 / schema_id is required")

        if self.confidence is not None:
            if not (0.0 <= self.confidence <= 1.0):
                raise ValueError("confidence 必须在 0~1 之间 / confidence must be in [0,1]")

    def _as_message(self) -> MessagePayload:
        if not isinstance(self.payload, MessagePayload):
            raise TypeError("payload 不是 MessagePayload")
        return self.payload

    def _as_world(self) -> WorldDataPayload:
        if not isinstance(self.payload, WorldDataPayload):
            raise TypeError("payload 不是 WorldDataPayload")
        return self.payload


# ============================================================
# 便捷构造函数 / Convenience constructors
# ============================================================

def make_message_observation(
    *,
    source_name: str,
    session_key: Optional[str],
    actor_id: Optional[str],
    text: Optional[str],
    attachments: Optional[List[AttachmentRef]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Observation:
    """
    快速创建“消息类观察”
    Create a MESSAGE observation easily
    """
    obs = Observation(
        obs_type=ObservationType.MESSAGE,
        source_name=source_name,
        session_key=session_key,
        actor=Actor(actor_id=actor_id, actor_type="user" if actor_id else "unknown"),
        payload=MessagePayload(
            text=text,
            attachments=attachments or []
        ),
        metadata=metadata or {},
    )
    obs.validate()
    return obs
