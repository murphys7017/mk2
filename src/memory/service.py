# memory/service.py
# =========================
# 记忆服务（Memory Service）
# 提供高层次的记忆管理接口，整合事件、对话轮次、记忆条目等
# =========================

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ContextPack, EventRecord, MemoryItem, TurnRecord
from .stores import EventStore, MemoryStore, TurnStore

if TYPE_CHECKING:
    from src.schemas.observation import Observation


# =============================================================================
# MemoryService - 记忆服务
# =============================================================================

class MemoryService:
    """
    记忆服务（Memory Service）
    
    提供高层次的记忆管理接口：
    - 事件记录管理
    - 对话轮次管理
    - 记忆条目管理
    - 上下文构建
    - 会话历史查询
    
    未来可扩展：
    - 记忆检索与召回
    - 记忆压缩与归档
    - 跨会话记忆迁移
    - 记忆重要性评估
    """
    
    def __init__(
        self,
        event_store: EventStore,
        turn_store: TurnStore,
        memory_store: MemoryStore,
    ):
        """
        初始化记忆服务
        
        Args:
            event_store: 事件存储
            turn_store: 对话轮次存储
            memory_store: 记忆条目存储
        """
        self.event_store = event_store
        self.turn_store = turn_store
        self.memory_store = memory_store
    
    # =========================================================================
    # 事件管理 / Event Management
    # =========================================================================
    
    async def record_event(
        self,
        obs: Observation,
        gate_result: dict | None = None,
        meta: dict | None = None,
    ) -> EventRecord:
        """
        记录事件
        Record event
        
        Args:
            obs: 观察对象
            gate_result: Gate 处理结果（可选）
            meta: 元数据（可选）
            
        Returns:
            事件记录
        """
        raise NotImplementedError
    
    async def get_event(self, event_id: str) -> EventRecord | None:
        """
        获取事件记录
        Get event record
        
        Args:
            event_id: 事件 ID
            
        Returns:
            事件记录，如果不存在则返回 None
        """
        raise NotImplementedError
    
    async def get_recent_events(
        self,
        session_key: str,
        limit: int = 20,
    ) -> list[EventRecord]:
        """
        获取最近的事件记录
        Get recent event records
        
        Args:
            session_key: 会话键
            limit: 最大返回数量
            
        Returns:
            事件记录列表（按时间倒序）
        """
        raise NotImplementedError
    
    # =========================================================================
    # 对话轮次管理 / Turn Management
    # =========================================================================
    
    async def start_turn(
        self,
        session_key: str,
        input_event_id: str,
        plan: dict | None = None,
    ) -> TurnRecord:
        """
        开始新的对话轮次
        Start a new turn
        
        Args:
            session_key: 会话键
            input_event_id: 输入事件 ID
            plan: 计划（可选）
            
        Returns:
            对话轮次记录
        """
        raise NotImplementedError
    
    async def finish_turn(
        self,
        turn_id: str,
        final_output_obs_id: str | None = None,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        """
        结束对话轮次
        Finish a turn
        
        Args:
            turn_id: 对话轮次 ID
            final_output_obs_id: 最终输出观察 ID（可选）
            status: 状态（ok / error / timeout）
            error: 错误信息（可选）
        """
        raise NotImplementedError
    
    async def add_tool_call_to_turn(
        self,
        turn_id: str,
        tool_call: dict,
        tool_result: dict | None = None,
    ) -> None:
        """
        向对话轮次添加工具调用
        Add tool call to turn
        
        Args:
            turn_id: 对话轮次 ID
            tool_call: 工具调用信息
            tool_result: 工具执行结果（可选）
        """
        raise NotImplementedError
    
    async def get_turn(self, turn_id: str) -> TurnRecord | None:
        """
        获取对话轮次记录
        Get turn record
        
        Args:
            turn_id: 对话轮次 ID
            
        Returns:
            对话轮次记录，如果不存在则返回 None
        """
        raise NotImplementedError
    
    async def get_recent_turns(
        self,
        session_key: str,
        limit: int = 10,
    ) -> list[TurnRecord]:
        """
        获取最近的对话轮次记录
        Get recent turn records
        
        Args:
            session_key: 会话键
            limit: 最大返回数量
            
        Returns:
            对话轮次记录列表（按时间倒序）
        """
        raise NotImplementedError
    
    # =========================================================================
    # 记忆条目管理 / Memory Item Management
    # =========================================================================
    
    async def save_memory(
        self,
        scope: str,
        kind: str,
        key: str,
        content: str,
        data: dict | None = None,
        confidence: float = 1.0,
        ttl_sec: int | None = None,
        source: str = "unknown",
    ) -> MemoryItem:
        """
        保存记忆条目
        Save memory item
        
        Args:
            scope: 作用域（persona / user / session / episodic / global）
            kind: 类型（fact / preference / goal / constraint ...）
            key: 唯一标识
            content: 文本描述
            data: 结构化数据（可选）
            confidence: 可信度 [0, 1]
            ttl_sec: 生存时间（秒，可选）
            source: 来源
            
        Returns:
            记忆条目
        """
        raise NotImplementedError
    
    async def get_memory(
        self,
        scope: str,
        kind: str,
        key: str,
    ) -> MemoryItem | None:
        """
        获取记忆条目
        Get memory item
        
        Args:
            scope: 作用域
            kind: 类型
            key: 唯一标识
            
        Returns:
            记忆条目，如果不存在则返回 None
        """
        raise NotImplementedError
    
    async def update_memory(
        self,
        scope: str,
        kind: str,
        key: str,
        content: str | None = None,
        data: dict | None = None,
        confidence: float | None = None,
    ) -> bool:
        """
        更新记忆条目
        Update memory item
        
        Args:
            scope: 作用域
            kind: 类型
            key: 唯一标识
            content: 新的文本描述（可选）
            data: 新的结构化数据（可选）
            confidence: 新的可信度（可选）
            
        Returns:
            是否更新成功
        """
        raise NotImplementedError
    
    async def delete_memory(
        self,
        scope: str,
        kind: str,
        key: str,
    ) -> bool:
        """
        删除记忆条目
        Delete memory item
        
        Args:
            scope: 作用域
            kind: 类型
            key: 唯一标识
            
        Returns:
            是否删除成功
        """
        raise NotImplementedError
    
    async def search_memories(
        self,
        query: str,
        scope: str | None = None,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """
        搜索记忆条目
        Search memory items
        
        Args:
            query: 搜索查询
            scope: 作用域（可选）
            kind: 类型（可选）
            limit: 最大返回数量
            
        Returns:
            记忆条目列表
        """
        raise NotImplementedError
    
    # =========================================================================
    # 上下文构建 / Context Building
    # =========================================================================
    
    async def build_context_pack(
        self,
        session_key: str,
        include_persona: bool = True,
        include_user_profile: bool = True,
        include_session_items: bool = True,
        include_episodic_items: bool = False,
        recent_events_limit: int = 10,
        recent_turns_limit: int = 5,
    ) -> ContextPack:
        """
        构建上下文包
        Build context pack
        
        Args:
            session_key: 会话键
            include_persona: 是否包含 persona 记忆
            include_user_profile: 是否包含用户画像记忆
            include_session_items: 是否包含会话级记忆
            include_episodic_items: 是否包含情景记忆
            recent_events_limit: 最近事件数量限制
            recent_turns_limit: 最近对话轮次数量限制
            
        Returns:
            上下文包
        """
        raise NotImplementedError
    
    async def build_lightweight_context(
        self,
        session_key: str,
        max_events: int = 5,
        max_turns: int = 3,
    ) -> ContextPack:
        """
        构建轻量级上下文包（仅最近历史，不含记忆）
        Build lightweight context pack (recent history only, no memory)
        
        Args:
            session_key: 会话键
            max_events: 最大事件数量
            max_turns: 最大对话轮次数量
            
        Returns:
            上下文包
        """
        raise NotImplementedError
    
    # =========================================================================
    # 会话管理 / Session Management
    # =========================================================================
    
    async def get_session_summary(
        self,
        session_key: str,
    ) -> dict:
        """
        获取会话摘要
        Get session summary
        
        Args:
            session_key: 会话键
            
        Returns:
            会话摘要（包含事件数、轮次数、记忆条目数等统计信息）
        """
        raise NotImplementedError
    
    async def clear_session(
        self,
        session_key: str,
        clear_events: bool = True,
        clear_turns: bool = True,
        clear_session_memories: bool = True,
    ) -> dict:
        """
        清理会话数据
        Clear session data
        
        Args:
            session_key: 会话键
            clear_events: 是否清理事件记录
            clear_turns: 是否清理对话轮次记录
            clear_session_memories: 是否清理会话级记忆条目
            
        Returns:
            清理结果（包含删除的各类记录数）
        """
        raise NotImplementedError
    
    async def archive_session(
        self,
        session_key: str,
    ) -> str:
        """
        归档会话（导出为 JSON，可用于备份或迁移）
        Archive session (export as JSON for backup or migration)
        
        Args:
            session_key: 会话键
            
        Returns:
            归档数据（JSON 字符串）
        """
        raise NotImplementedError
    
    async def restore_session(
        self,
        archive_data: str,
    ) -> str:
        """
        还原会话（从归档数据恢复）
        Restore session (from archive data)
        
        Args:
            archive_data: 归档数据（JSON 字符串）
            
        Returns:
            恢复的会话键
        """
        raise NotImplementedError
    
    # =========================================================================
    # 维护与管理 / Maintenance & Management
    # =========================================================================
    
    async def cleanup_expired_memories(self) -> int:
        """
        清理过期的记忆条目
        Cleanup expired memory items
        
        Returns:
            清理的记录数
        """
        raise NotImplementedError
    
    async def health_check(self) -> dict:
        """
        健康检查
        Health check
        
        Returns:
            健康状态信息
        """
        raise NotImplementedError
