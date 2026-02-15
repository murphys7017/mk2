# memory/stores.py
# =========================
# 存储协议接口（Store Protocol Interfaces）
# 定义事件存储、对话轮次存储、记忆条目存储的协议
# =========================

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import EventRecord, TurnRecord, MemoryItem


# =============================================================================
# EventStore - 事件存储协议
# =============================================================================

@runtime_checkable
class EventStore(Protocol):
    """
    事件存储协议（Event Store Protocol）
    
    存储和检索 EventRecord
    Store and retrieve EventRecord
    """
    
    async def save_event(self, event: EventRecord) -> None:
        """
        保存事件记录
        Save event record
        
        Args:
            event: 事件记录
        """
        ...
    
    async def get_event(self, event_id: str) -> EventRecord | None:
        """
        根据 event_id 获取事件记录
        Get event record by event_id
        
        Args:
            event_id: 事件 ID
            
        Returns:
            事件记录，如果不存在则返回 None
        """
        ...
    
    async def list_events_by_session(
        self,
        session_key: str,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "ts",
        descending: bool = True,
    ) -> list[EventRecord]:
        """
        列出指定会话的事件记录
        List event records by session
        
        Args:
            session_key: 会话键
            limit: 最大返回数量
            offset: 偏移量
            order_by: 排序字段（默认按时间戳）
            descending: 是否降序（默认最新的在前）
            
        Returns:
            事件记录列表
        """
        ...
    
    async def list_events_by_time_range(
        self,
        session_key: str | None,
        start_ts: float,
        end_ts: float,
        limit: int = 100,
    ) -> list[EventRecord]:
        """
        列出指定时间范围的事件记录
        List event records by time range
        
        Args:
            session_key: 会话键（None 表示所有会话）
            start_ts: 开始时间戳
            end_ts: 结束时间戳
            limit: 最大返回数量
            
        Returns:
            事件记录列表
        """
        ...
    
    async def delete_events_by_session(self, session_key: str) -> int:
        """
        删除指定会话的所有事件记录
        Delete all event records by session
        
        Args:
            session_key: 会话键
            
        Returns:
            删除的记录数
        """
        ...
    
    async def count_events_by_session(self, session_key: str) -> int:
        """
        统计指定会话的事件记录数
        Count event records by session
        
        Args:
            session_key: 会话键
            
        Returns:
            事件记录数
        """
        ...


# =============================================================================
# TurnStore - 对话轮次存储协议
# =============================================================================

@runtime_checkable
class TurnStore(Protocol):
    """
    对话轮次存储协议（Turn Store Protocol）
    
    存储和检索 TurnRecord
    Store and retrieve TurnRecord
    """
    
    async def save_turn(self, turn: TurnRecord) -> None:
        """
        保存对话轮次记录
        Save turn record
        
        Args:
            turn: 对话轮次记录
        """
        ...
    
    async def get_turn(self, turn_id: str) -> TurnRecord | None:
        """
        根据 turn_id 获取对话轮次记录
        Get turn record by turn_id
        
        Args:
            turn_id: 对话轮次 ID
            
        Returns:
            对话轮次记录，如果不存在则返回 None
        """
        ...
    
    async def list_turns_by_session(
        self,
        session_key: str,
        limit: int = 50,
        offset: int = 0,
        descending: bool = True,
    ) -> list[TurnRecord]:
        """
        列出指定会话的对话轮次记录
        List turn records by session
        
        Args:
            session_key: 会话键
            limit: 最大返回数量
            offset: 偏移量
            descending: 是否降序（默认最新的在前）
            
        Returns:
            对话轮次记录列表
        """
        ...
    
    async def update_turn_status(
        self,
        turn_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """
        更新对话轮次状态
        Update turn status
        
        Args:
            turn_id: 对话轮次 ID
            status: 状态（ok / error / timeout ...）
            error: 错误信息（可选）
        """
        ...
    
    async def delete_turns_by_session(self, session_key: str) -> int:
        """
        删除指定会话的所有对话轮次记录
        Delete all turn records by session
        
        Args:
            session_key: 会话键
            
        Returns:
            删除的记录数
        """
        ...
    
    async def count_turns_by_session(self, session_key: str) -> int:
        """
        统计指定会话的对话轮次记录数
        Count turn records by session
        
        Args:
            session_key: 会话键
            
        Returns:
            对话轮次记录数
        """
        ...


# =============================================================================
# MemoryStore - 记忆条目存储协议
# =============================================================================

@runtime_checkable
class MemoryStore(Protocol):
    """
    记忆条目存储协议（Memory Store Protocol）
    
    存储和检索 MemoryItem
    Store and retrieve MemoryItem
    """
    
    async def save_memory(self, item: MemoryItem) -> None:
        """
        保存记忆条目
        Save memory item
        
        Args:
            item: 记忆条目
        """
        ...
    
    async def get_memory(self, scope: str, kind: str, key: str) -> MemoryItem | None:
        """
        根据 (scope, kind, key) 获取记忆条目
        Get memory item by (scope, kind, key)
        
        Args:
            scope: 作用域（persona / user / session / episodic / global）
            kind: 类型（fact / preference / goal / constraint ...）
            key: 唯一标识
            
        Returns:
            记忆条目，如果不存在则返回 None
        """
        ...
    
    async def list_memories_by_scope(
        self,
        scope: str,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[MemoryItem]:
        """
        列出指定作用域的记忆条目
        List memory items by scope
        
        Args:
            scope: 作用域
            kind: 类型（可选，None 表示所有类型）
            limit: 最大返回数量
            
        Returns:
            记忆条目列表
        """
        ...
    
    async def update_memory(
        self,
        scope: str,
        kind: str,
        key: str,
        content: str | None = None,
        data: dict | None = None,
        confidence: float | None = None,
    ) -> None:
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
        """
        ...
    
    async def delete_memory(self, scope: str, kind: str, key: str) -> bool:
        """
        删除记忆条目
        Delete memory item
        
        Args:
            scope: 作用域
            kind: 类型
            key: 唯一标识
            
        Returns:
            是否删除成功（如果记录不存在则返回 False）
        """
        ...
    
    async def delete_memories_by_scope(self, scope: str, kind: str | None = None) -> int:
        """
        删除指定作用域的记忆条目
        Delete memory items by scope
        
        Args:
            scope: 作用域
            kind: 类型（可选，None 表示删除所有类型）
            
        Returns:
            删除的记录数
        """
        ...
    
    async def search_memories(
        self,
        query: str,
        scope: str | None = None,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """
        搜索记忆条目（基于文本内容）
        Search memory items (by text content)
        
        Args:
            query: 搜索查询
            scope: 作用域（可选）
            kind: 类型（可选）
            limit: 最大返回数量
            
        Returns:
            记忆条目列表
        """
        ...
    
    async def cleanup_expired_memories(self, now_ts: float | None = None) -> int:
        """
        清理过期的记忆条目
        Cleanup expired memory items
        
        Args:
            now_ts: 当前时间戳（可选，默认使用 time.time()）
            
        Returns:
            清理的记录数
        """
        ...
