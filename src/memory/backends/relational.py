# memory/backends/relational.py
# =========================
# 关系数据库后端（SQLAlchemy）
# 支持 MySQL 和 SQLite fallback
# =========================

from __future__ import annotations

import json
import time
from typing import Optional, Protocol, Any, TYPE_CHECKING

try:
    from sqlalchemy import (
        create_engine,
        Column,
        String,
        Float,
        Text,
        DateTime,
        Integer,
        func,
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, Session
    from sqlalchemy.pool import StaticPool
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False
    # 为类型检查器提供存根
    if TYPE_CHECKING:
        from sqlalchemy import (
            create_engine,
            Column,
            String,
            Float,
            Text,
            DateTime,
            Integer,
            func,
        )
        from sqlalchemy.orm import declarative_base, sessionmaker, Session
        from sqlalchemy.pool import StaticPool


if HAS_SQLALCHEMY:
    Base = declarative_base()
    
    class EventTable(Base):
        """Events 表"""
        __tablename__ = "events"
        
        event_id = Column(String(128), primary_key=True)
        session_key = Column(String(255), index=True)
        ts = Column(Float, index=True)
        obs_json = Column(Text)
        gate_json = Column(Text, nullable=True)
        meta_json = Column(Text)
        created_at = Column(DateTime, server_default=func.now())
    
    class TurnTable(Base):
        """Turns 表"""
        __tablename__ = "turns"
        
        turn_id = Column(String(128), primary_key=True)
        session_key = Column(String(255), index=True)
        started_ts = Column(Float, nullable=True, index=True)
        finished_ts = Column(Float, nullable=True)
        input_event_id = Column(String(128))
        plan_json = Column(Text, nullable=True)
        tool_calls_json = Column(Text)
        tool_results_json = Column(Text)
        final_output_obs_id = Column(String(128), nullable=True)
        status = Column(String(32), default="ok")
        error = Column(Text, nullable=True)
        meta_json = Column(Text)
        created_at = Column(DateTime, server_default=func.now())
    
    class ConfigTable(Base):
        """Config 配置表（全文存储）"""
        __tablename__ = "configs"
        
        config_key = Column(String(255), primary_key=True)
        content = Column(Text)
        frontmatter_json = Column(Text)
        md5 = Column(String(32), index=True)
        updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
        created_at = Column(DateTime, server_default=func.now())
    
    class KnowledgeTable(Base):
        """Knowledge 知识表（片段索引）"""
        __tablename__ = "knowledge"
        
        knowledge_key = Column(String(255), primary_key=True)
        content = Column(Text)
        frontmatter_json = Column(Text)
        md5 = Column(String(32), index=True)
        updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
        created_at = Column(DateTime, server_default=func.now())


# =============================================================================
# RelationalBackend Protocol
# =============================================================================

class RelationalBackend(Protocol):
    """
    关系数据库后端协议
    """
    
    def initialize(self) -> None:
        """初始化后端（创建表等）"""
        ...
    
    def close(self) -> None:
        """关闭连接"""
        ...
    
    def save_event_dict(self, event_dict: dict) -> None:
        """保存事件（dict 格式）"""
        ...
    
    def get_event_dict(self, event_id: str) -> Optional[dict]:
        """获取事件"""
        ...
    
    def list_events_by_session(
        self,
        session_key: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出会话的事件"""
        ...
    
    def save_turn_dict(self, turn_dict: dict) -> None:
        """保存对话轮次"""
        ...
    
    def get_turn_dict(self, turn_id: str) -> Optional[dict]:
        """获取对话轮次"""
        ...
    
    def list_turns_by_session(
        self,
        session_key: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出会话的对话轮次"""
        ...
    
    def update_turn_status(
        self,
        turn_id: str,
        status: str,
        error: Optional[str] = None,
        final_output_obs_id: Optional[str] = None,
        finished_ts: Optional[float] = None,
    ) -> None:
        """更新对话轮次状态"""
        ...
    
    def save_config_dict(self, config_dict: dict) -> None:
        """保存配置"""
        ...
    
    def get_config_dict(self, config_key: str) -> Optional[dict]:
        """获取配置"""
        ...
    
    def save_knowledge_dict(self, knowledge_dict: dict) -> None:
        """保存知识条目"""
        ...
    
    def get_knowledge_dict(self, knowledge_key: str) -> Optional[dict]:
        """获取知识条目"""
        ...

    def delete_knowledge_dict(self, knowledge_key: str) -> bool:
        """删除知识条目"""
        ...
    
    # =========================================================================
    # 增强查询方法
    # =========================================================================
    
    def list_events_by_time_range(
        self,
        session_key: str,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按时间范围查询事件"""
        ...
    
    def list_events_by_actor(
        self,
        session_key: str,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按actor查询事件"""
        ...
    
    def list_turns_by_status(
        self,
        session_key: str,
        status: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按状态查询对话轮次"""
        ...
    
    def get_turn_with_events(self, turn_id: str) -> Optional[dict]:
        """获取对话轮次及其关联的所有事件"""
        ...
    
    def search_events_by_content(
        self,
        session_key: str,
        search_text: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """在事件内容中模糊搜索"""
        ...
    
    def search_turns_by_content(
        self,
        session_key: str,
        search_text: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """在对话轮次内容中模糊搜索"""
        ...
    
    def count_events_by_session(self, session_key: str) -> int:
        """统计会话的事件数量"""
        ...
    
    def count_turns_by_session(self, session_key: str) -> int:
        """统计会话的对话轮次数量"""
        ...


# =============================================================================
# SQLAlchemy 实现
# =============================================================================

class SQLAlchemyBackend:
    """基于 SQLAlchemy 的关系数据库后端"""
    
    def __init__(
        self,
        dsn: str,
        pool_size: Optional[int] = None,
        max_overflow: Optional[int] = None,
    ):
        """
        初始化后端
        
        Args:
            dsn: 数据库连接字符串（如 mysql+pymysql://user:pass@host/db）
            pool_size: 连接池大小（适用于非 SQLite）
            max_overflow: 连接池溢出大小（适用于非 SQLite）
        """
        if not HAS_SQLALCHEMY:
            raise ImportError("SQLAlchemy not installed")
        
        self.dsn = dsn
        
        # 处理 SQLite in-memory 特殊情况（用于测试）
        if dsn == "sqlite:///:memory:":
            self.engine = create_engine(
                dsn,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
            if not dsn.startswith("sqlite"):
                if pool_size is not None:
                    engine_kwargs["pool_size"] = pool_size
                if max_overflow is not None:
                    engine_kwargs["max_overflow"] = max_overflow
            self.engine = create_engine(dsn, **engine_kwargs)
        
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def initialize(self) -> None:
        """创建表"""
        Base.metadata.create_all(self.engine)
    
    def close(self) -> None:
        """关闭连接池"""
        self.engine.dispose()
    
    def save_event_dict(self, event_dict: dict) -> None:
        """保存事件"""
        session = self.SessionLocal()
        try:
            event = EventTable(
                event_id=event_dict["event_id"],
                session_key=event_dict["session_key"],
                ts=event_dict["ts"],
                obs_json=event_dict["obs_json"],
                gate_json=event_dict.get("gate_json"),
                meta_json=event_dict.get("meta_json", "{}"),
            )
            session.merge(event)  # 使用 merge 避免重复插入
            session.commit()
        finally:
            session.close()
    
    def get_event_dict(self, event_id: str) -> Optional[dict]:
        """获取事件"""
        session = self.SessionLocal()
        try:
            event = session.query(EventTable).filter_by(event_id=event_id).first()
            if not event:
                return None
            
            return {
                "event_id": event.event_id,
                "session_key": event.session_key,
                "ts": event.ts,
                "obs_json": event.obs_json,
                "gate_json": event.gate_json,
                "meta_json": event.meta_json,
            }
        finally:
            session.close()
    
    def list_events_by_session(
        self,
        session_key: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出会话的事件"""
        session = self.SessionLocal()
        try:
            events = (
                session.query(EventTable)
                .filter_by(session_key=session_key)
                .order_by(EventTable.ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "event_id": e.event_id,
                    "session_key": e.session_key,
                    "ts": e.ts,
                    "obs_json": e.obs_json,
                    "gate_json": e.gate_json,
                    "meta_json": e.meta_json,
                }
                for e in events
            ]
        finally:
            session.close()
    
    def save_turn_dict(self, turn_dict: dict) -> None:
        """保存对话轮次"""
        session = self.SessionLocal()
        try:
            turn = TurnTable(
                turn_id=turn_dict["turn_id"],
                session_key=turn_dict["session_key"],
                started_ts=turn_dict.get("started_ts"),
                finished_ts=turn_dict.get("finished_ts"),
                input_event_id=turn_dict["input_event_id"],
                plan_json=turn_dict.get("plan_json"),
                tool_calls_json=turn_dict.get("tool_calls_json", "[]"),
                tool_results_json=turn_dict.get("tool_results_json", "[]"),
                final_output_obs_id=turn_dict.get("final_output_obs_id"),
                status=turn_dict.get("status", "ok"),
                error=turn_dict.get("error"),
                meta_json=turn_dict.get("meta_json", "{}"),
            )
            session.merge(turn)
            session.commit()
        finally:
            session.close()
    
    def get_turn_dict(self, turn_id: str) -> Optional[dict]:
        """获取对话轮次"""
        session = self.SessionLocal()
        try:
            turn = session.query(TurnTable).filter_by(turn_id=turn_id).first()
            if not turn:
                return None
            
            return {
                "turn_id": turn.turn_id,
                "session_key": turn.session_key,
                "started_ts": turn.started_ts,
                "finished_ts": turn.finished_ts,
                "input_event_id": turn.input_event_id,
                "plan_json": turn.plan_json,
                "tool_calls_json": turn.tool_calls_json,
                "tool_results_json": turn.tool_results_json,
                "final_output_obs_id": turn.final_output_obs_id,
                "status": turn.status,
                "error": turn.error,
                "meta_json": turn.meta_json,
            }
        finally:
            session.close()
    
    def list_turns_by_session(
        self,
        session_key: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """列出会话的对话轮次"""
        session = self.SessionLocal()
        try:
            turns = (
                session.query(TurnTable)
                .filter_by(session_key=session_key)
                .order_by(TurnTable.started_ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "turn_id": t.turn_id,
                    "session_key": t.session_key,
                    "started_ts": t.started_ts,
                    "finished_ts": t.finished_ts,
                    "input_event_id": t.input_event_id,
                    "plan_json": t.plan_json,
                    "tool_calls_json": t.tool_calls_json,
                    "tool_results_json": t.tool_results_json,
                    "final_output_obs_id": t.final_output_obs_id,
                    "status": t.status,
                    "error": t.error,
                    "meta_json": t.meta_json,
                }
                for t in turns
            ]
        finally:
            session.close()
    
    def update_turn_status(
        self,
        turn_id: str,
        status: str,
        error: Optional[str] = None,
        final_output_obs_id: Optional[str] = None,
        finished_ts: Optional[float] = None,
    ) -> None:
        """更新对话轮次状态"""
        session = self.SessionLocal()
        try:
            turn = session.query(TurnTable).filter_by(turn_id=turn_id).first()
            if turn:
                turn.status = status  # type: ignore[assignment]
                # 允许显式清空 error，避免保留历史错误
                turn.error = error  # type: ignore[assignment]
                if final_output_obs_id is not None:
                    turn.final_output_obs_id = final_output_obs_id  # type: ignore[assignment]
                turn.finished_ts = finished_ts or time.time()  # type: ignore[assignment]
                session.commit()
        finally:
            session.close()
    
    def save_config_dict(self, config_dict: dict) -> None:
        """保存配置"""
        session = self.SessionLocal()
        try:
            config = ConfigTable(
                config_key=config_dict["config_key"],
                content=config_dict["content"],
                frontmatter_json=config_dict.get("frontmatter_json", "{}"),
                md5=config_dict["md5"],
            )
            session.merge(config)  # 使用 merge 避免重复插入
            session.commit()
        finally:
            session.close()
    
    def get_config_dict(self, config_key: str) -> Optional[dict]:
        """获取配置"""
        session = self.SessionLocal()
        try:
            config = session.query(ConfigTable).filter_by(config_key=config_key).first()
            if not config:
                return None
            
            return {
                "config_key": config.config_key,
                "content": config.content,
                "frontmatter_json": config.frontmatter_json,
                "md5": config.md5,
                "updated_at": config.updated_at.isoformat() if config.updated_at is not None else None,  # type: ignore[union-attr]
                "created_at": config.created_at.isoformat() if config.created_at is not None else None,  # type: ignore[union-attr]
            }
        finally:
            session.close()
    
    def save_knowledge_dict(self, knowledge_dict: dict) -> None:
        """保存知识条目"""
        session = self.SessionLocal()
        try:
            knowledge = KnowledgeTable(
                knowledge_key=knowledge_dict["knowledge_key"],
                content=knowledge_dict["content"],
                frontmatter_json=knowledge_dict.get("frontmatter_json", "{}"),
                md5=knowledge_dict["md5"],
            )
            session.merge(knowledge)
            session.commit()
        finally:
            session.close()
    
    def get_knowledge_dict(self, knowledge_key: str) -> Optional[dict]:
        """获取知识条目"""
        session = self.SessionLocal()
        try:
            knowledge = session.query(KnowledgeTable).filter_by(knowledge_key=knowledge_key).first()
            if not knowledge:
                return None
            
            return {
                "knowledge_key": knowledge.knowledge_key,
                "content": knowledge.content,
                "frontmatter_json": knowledge.frontmatter_json,
                "md5": knowledge.md5,
                "updated_at": knowledge.updated_at.isoformat() if knowledge.updated_at is not None else None,  # type: ignore[union-attr]
                "created_at": knowledge.created_at.isoformat() if knowledge.created_at is not None else None,  # type: ignore[union-attr]
            }
        finally:
            session.close()

    def delete_knowledge_dict(self, knowledge_key: str) -> bool:
        """删除知识条目"""
        session = self.SessionLocal()
        try:
            rows = session.query(KnowledgeTable).filter_by(knowledge_key=knowledge_key).delete()
            session.commit()
            return rows > 0
        finally:
            session.close()
    
    # =========================================================================
    # 增强查询方法实现
    # =========================================================================
    
    def list_events_by_time_range(
        self,
        session_key: str,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按时间范围查询事件"""
        session = self.SessionLocal()
        try:
            query = session.query(EventTable).filter_by(session_key=session_key)
            
            if start_ts is not None:
                query = query.filter(EventTable.ts >= start_ts)
            if end_ts is not None:
                query = query.filter(EventTable.ts <= end_ts)
            
            events = (
                query.order_by(EventTable.ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "event_id": e.event_id,
                    "session_key": e.session_key,
                    "ts": e.ts,
                    "obs_json": e.obs_json,
                    "gate_json": e.gate_json,
                    "meta_json": e.meta_json,
                }
                for e in events
            ]
        finally:
            session.close()
    
    def list_events_by_actor(
        self,
        session_key: str,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按actor查询事件（通过obs_json中的actor字段）"""
        session = self.SessionLocal()
        try:
            query = session.query(EventTable).filter_by(session_key=session_key)
            
            # 使用 LIKE 查询 JSON 字段中的 actor 信息
            # 注意：这种方式在大数据量时性能较差，建议使用 JSON 字段或单独的 actor 列
            if actor_id:
                query = query.filter(EventTable.obs_json.like(f'%"actor_id": "{actor_id}"%'))
            if actor_type:
                query = query.filter(EventTable.obs_json.like(f'%"actor_type": "{actor_type}"%'))
            
            events = (
                query.order_by(EventTable.ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "event_id": e.event_id,
                    "session_key": e.session_key,
                    "ts": e.ts,
                    "obs_json": e.obs_json,
                    "gate_json": e.gate_json,
                    "meta_json": e.meta_json,
                }
                for e in events
            ]
        finally:
            session.close()
    
    def list_turns_by_status(
        self,
        session_key: str,
        status: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按状态查询对话轮次"""
        session = self.SessionLocal()
        try:
            turns = (
                session.query(TurnTable)
                .filter_by(session_key=session_key, status=status)
                .order_by(TurnTable.started_ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "turn_id": t.turn_id,
                    "session_key": t.session_key,
                    "started_ts": t.started_ts,
                    "finished_ts": t.finished_ts,
                    "input_event_id": t.input_event_id,
                    "plan_json": t.plan_json,
                    "tool_calls_json": t.tool_calls_json,
                    "tool_results_json": t.tool_results_json,
                    "final_output_obs_id": t.final_output_obs_id,
                    "status": t.status,
                    "error": t.error,
                    "meta_json": t.meta_json,
                }
                for t in turns
            ]
        finally:
            session.close()
    
    def get_turn_with_events(self, turn_id: str) -> Optional[dict]:
        """获取对话轮次及其关联的所有事件"""
        session = self.SessionLocal()
        try:
            turn = session.query(TurnTable).filter_by(turn_id=turn_id).first()
            if not turn:
                return None
            
            # 收集关联的 event_ids
            event_ids = []
            if turn.input_event_id is not None:  # type: ignore[comparison-overlap]
                event_ids.append(turn.input_event_id)
            if turn.final_output_obs_id is not None:  # type: ignore[comparison-overlap]
                event_ids.append(turn.final_output_obs_id)
            
            # 从 tool_results_json 中提取事件ID（如果有的话）
            try:
                import json
                tool_results_json: str = turn.tool_results_json or "[]"  # type: ignore[assignment]
                tool_results = json.loads(tool_results_json)
                for result in tool_results:
                    if isinstance(result, dict) and "event_id" in result:
                        event_ids.append(result["event_id"])
            except:
                pass
            
            # 查询所有关联的事件
            events = []
            if event_ids:
                events = session.query(EventTable).filter(EventTable.event_id.in_(event_ids)).all()
            
            return {
                "turn": {
                    "turn_id": turn.turn_id,
                    "session_key": turn.session_key,
                    "started_ts": turn.started_ts,
                    "finished_ts": turn.finished_ts,
                    "input_event_id": turn.input_event_id,
                    "plan_json": turn.plan_json,
                    "tool_calls_json": turn.tool_calls_json,
                    "tool_results_json": turn.tool_results_json,
                    "final_output_obs_id": turn.final_output_obs_id,
                    "status": turn.status,
                    "error": turn.error,
                    "meta_json": turn.meta_json,
                },
                "events": [
                    {
                        "event_id": e.event_id,
                        "session_key": e.session_key,
                        "ts": e.ts,
                        "obs_json": e.obs_json,
                        "gate_json": e.gate_json,
                        "meta_json": e.meta_json,
                    }
                    for e in events
                ],
            }
        finally:
            session.close()
    
    def search_events_by_content(
        self,
        session_key: str,
        search_text: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """在事件内容中模糊搜索"""
        session = self.SessionLocal()
        try:
            # 在 obs_json, gate_json, meta_json 中搜索
            search_pattern = f"%{search_text}%"
            events = (
                session.query(EventTable)
                .filter_by(session_key=session_key)
                .filter(
                    (EventTable.obs_json.like(search_pattern)) |
                    (EventTable.gate_json.like(search_pattern)) |
                    (EventTable.meta_json.like(search_pattern))
                )
                .order_by(EventTable.ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "event_id": e.event_id,
                    "session_key": e.session_key,
                    "ts": e.ts,
                    "obs_json": e.obs_json,
                    "gate_json": e.gate_json,
                    "meta_json": e.meta_json,
                }
                for e in events
            ]
        finally:
            session.close()
    
    def search_turns_by_content(
        self,
        session_key: str,
        search_text: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """在对话轮次内容中模糊搜索"""
        session = self.SessionLocal()
        try:
            # 在 plan_json, tool_calls_json, tool_results_json, error, meta_json 中搜索
            search_pattern = f"%{search_text}%"
            turns = (
                session.query(TurnTable)
                .filter_by(session_key=session_key)
                .filter(
                    (TurnTable.plan_json.like(search_pattern)) |
                    (TurnTable.tool_calls_json.like(search_pattern)) |
                    (TurnTable.tool_results_json.like(search_pattern)) |
                    (TurnTable.error.like(search_pattern)) |
                    (TurnTable.meta_json.like(search_pattern))
                )
                .order_by(TurnTable.started_ts.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            
            return [
                {
                    "turn_id": t.turn_id,
                    "session_key": t.session_key,
                    "started_ts": t.started_ts,
                    "finished_ts": t.finished_ts,
                    "input_event_id": t.input_event_id,
                    "plan_json": t.plan_json,
                    "tool_calls_json": t.tool_calls_json,
                    "tool_results_json": t.tool_results_json,
                    "final_output_obs_id": t.final_output_obs_id,
                    "status": t.status,
                    "error": t.error,
                    "meta_json": t.meta_json,
                }
                for t in turns
            ]
        finally:
            session.close()
    
    def count_events_by_session(self, session_key: str) -> int:
        """统计会话的事件数量"""
        session = self.SessionLocal()
        try:
            count = session.query(EventTable).filter_by(session_key=session_key).count()
            return count
        finally:
            session.close()
    
    def count_turns_by_session(self, session_key: str) -> int:
        """统计会话的对话轮次数量"""
        session = self.SessionLocal()
        try:
            count = session.query(TurnTable).filter_by(session_key=session_key).count()
            return count
        finally:
            session.close()

