# memory/backend.py
# =========================
# 存储后端协议（Storage Backend Protocol）
# 定义底层存储后端的抽象接口，支持 SQLite / JSONL / 内存等实现
# =========================

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# =============================================================================
# StorageBackend - 存储后端协议
# =============================================================================

@runtime_checkable
class StorageBackend(Protocol):
    """
    存储后端协议（Storage Backend Protocol）
    
    提供底层的 CRUD 操作接口，供 Store 层使用
    Provides low-level CRUD operations for Store layer
    
    支持多种实现：
    - SQLiteBackend：基于 SQLite 的持久化存储
    - JSONLBackend：基于 JSONL 文件的追加式存储
    - InMemoryBackend：基于内存的临时存储
    - RedisBackend：基于 Redis 的分布式存储
    """
    
    async def initialize(self) -> None:
        """
        初始化后端（创建表 / 文件 / 连接等）
        Initialize backend (create tables / files / connections)
        """
        ...
    
    async def close(self) -> None:
        """
        关闭后端（释放资源 / 关闭连接等）
        Close backend (release resources / close connections)
        """
        ...
    
    async def insert(
        self,
        collection: str,
        data: dict[str, Any],
    ) -> None:
        """
        插入记录
        Insert record
        
        Args:
            collection: 集合/表名（如 "events", "turns", "memories"）
            data: 要插入的数据（字典格式）
        """
        ...
    
    async def get(
        self,
        collection: str,
        key: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        根据主键获取记录
        Get record by primary key
        
        Args:
            collection: 集合/表名
            key: 主键字典（如 {"event_id": "xxx"}）
            
        Returns:
            记录数据（字典格式），如果不存在则返回 None
        """
        ...
    
    async def update(
        self,
        collection: str,
        key: dict[str, Any],
        data: dict[str, Any],
    ) -> bool:
        """
        更新记录
        Update record
        
        Args:
            collection: 集合/表名
            key: 主键字典
            data: 要更新的字段
            
        Returns:
            是否更新成功（如果记录不存在则返回 False）
        """
        ...
    
    async def delete(
        self,
        collection: str,
        key: dict[str, Any],
    ) -> bool:
        """
        删除记录
        Delete record
        
        Args:
            collection: 集合/表名
            key: 主键字典
            
        Returns:
            是否删除成功（如果记录不存在则返回 False）
        """
        ...
    
    async def query(
        self,
        collection: str,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        查询记录
        Query records
        
        Args:
            collection: 集合/表名
            filters: 过滤条件（字典格式，如 {"session_key": "abc"}）
            order_by: 排序字段
            descending: 是否降序
            limit: 最大返回数量
            offset: 偏移量
            
        Returns:
            记录列表（每条记录为字典格式）
        """
        ...
    
    async def count(
        self,
        collection: str,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """
        统计记录数
        Count records
        
        Args:
            collection: 集合/表名
            filters: 过滤条件
            
        Returns:
            记录数
        """
        ...
    
    async def delete_many(
        self,
        collection: str,
        filters: dict[str, Any],
    ) -> int:
        """
        批量删除记录
        Delete multiple records
        
        Args:
            collection: 集合/表名
            filters: 过滤条件
            
        Returns:
            删除的记录数
        """
        ...
    
    async def search_text(
        self,
        collection: str,
        text_field: str,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        文本搜索（可选功能，简单实现可用 LIKE，高级实现可用全文索引）
        Text search (optional feature, simple: LIKE, advanced: full-text index)
        
        Args:
            collection: 集合/表名
            text_field: 要搜索的文本字段
            query: 搜索查询
            filters: 额外的过滤条件
            limit: 最大返回数量
            
        Returns:
            记录列表
        """
        ...
    
    async def query_range(
        self,
        collection: str,
        range_field: str,
        start: Any,
        end: Any,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        范围查询（用于时间戳等）
        Range query (for timestamps, etc.)
        
        Args:
            collection: 集合/表名
            range_field: 范围字段（如 "ts"）
            start: 起始值
            end: 结束值
            filters: 额外的过滤条件
            limit: 最大返回数量
            
        Returns:
            记录列表
        """
        ...
    
    async def health_check(self) -> dict[str, Any]:
        """
        健康检查
        Health check
        
        Returns:
            健康状态信息（如连接状态、存储空间等）
        """
        ...
