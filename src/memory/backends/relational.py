# memory/backends/relational.py
# =========================
# 关系数据库后端（SQLAlchemy）
# 支持 MySQL 和 SQLite fallback
# =========================

from __future__ import annotations

import json
import time
from typing import Optional, Protocol, Any

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
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.pool import StaticPool
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


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
    ) -> None:
        """更新对话轮次状态"""
        ...


# =============================================================================
# SQLAlchemy 实现
# =============================================================================

class SQLAlchemyBackend:
    """基于 SQLAlchemy 的关系数据库后端"""
    
    def __init__(self, dsn: str):
        """
        初始化后端
        
        Args:
            dsn: 数据库连接字符串（如 mysql+pymysql://user:pass@host/db）
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
            self.engine = create_engine(dsn, pool_pre_ping=True)
        
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
    ) -> None:
        """更新对话轮次状态"""
        session = self.SessionLocal()
        try:
            turn = session.query(TurnTable).filter_by(turn_id=turn_id).first()
            if turn:
                turn.status = status
                if error:
                    turn.error = error
                turn.finished_ts = time.time()
                session.commit()
        finally:
            session.close()

