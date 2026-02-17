# memory/service.py
# =========================
# 记忆服务（Memory Service - 完整实现）
# =========================

from __future__ import annotations

import json
import time
import logging
from typing import TYPE_CHECKING, Optional

from .models import ContextPack, EventRecord, MemoryItem, TurnRecord, MemoryScope
from .vault import MarkdownItemStore

if TYPE_CHECKING:
    from src.schemas.observation import Observation
    from .backends.relational import RelationalBackend
    from .backends.vector import VectorIndex, EmbeddingProvider

logger = logging.getLogger(__name__)


class MemoryService:
    """
    记忆服务（Memory Service）
    
    提供高层次的记忆管理接口，作为唯一入口。
    设计原则：Agent/Speaker 不允许直接从 bus 读取上下文。
    """
    
    def __init__(
        self,
        db_backend: RelationalBackend,
        markdown_vault_path: str = "memory_vault",
        vector_index: Optional[VectorIndex] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        """初始化记忆服务"""
        self.db_backend: RelationalBackend = db_backend
        self.markdown_store = MarkdownItemStore(markdown_vault_path)
        self.vector_index = vector_index
        if self.vector_index and embedding_provider and hasattr(self.vector_index, "embedding_provider"):
            self.vector_index.embedding_provider = embedding_provider
        self.db_backend.initialize()
        logger.info("MemoryService initialized")
    
    # ===== 事件管理 =====
    
    def append_event(
        self,
        obs: Observation,
        session_key: str,
        gate_result: Optional[dict] = None,
        meta: Optional[dict] = None,
    ) -> EventRecord:
        """记录事件"""
        event = EventRecord(
            event_id=f"evt_{int(time.time() * 1000)}_{obs.obs_id[:8]}",
            ts=time.time(),
            session_key=session_key,
            obs=obs,
            gate=gate_result,
            meta=meta or {},
        )
        event_dict = event.to_dict()
        # 将 obs 字段序列化为 obs_json
        event_dict['obs_json'] = json.dumps(event_dict.pop('obs'))
        # 将 gate 序列化为 gate_json
        if 'gate' in event_dict and event_dict['gate']:
            event_dict['gate_json'] = json.dumps(event_dict.pop('gate'))
        else:
            event_dict.pop('gate', None)
        # 将 meta 序列化为 meta_json
        if 'meta' in event_dict:
            event_dict['meta_json'] = json.dumps(event_dict.pop('meta'))
        self.db_backend.save_event_dict(event_dict)
        logger.debug(f"Event recorded: {event.event_id}")
        return event
    
    def get_event(self, event_id: str) -> Optional[EventRecord]:
        """获取事件记录"""
        event_dict = self.db_backend.get_event_dict(event_id)
        if not event_dict:
            return None
        # 反序列化 JSON 字段（总是删除这些字段）
        if 'obs_json' in event_dict:
            event_dict['obs'] = json.loads(event_dict.pop('obs_json'))
        if 'gate_json' in event_dict:
            gate_json = event_dict.pop('gate_json')
            if gate_json:
                event_dict['gate'] = json.loads(gate_json)
        if 'meta_json' in event_dict:
            event_dict['meta'] = json.loads(event_dict.pop('meta_json'))
        return EventRecord.from_dict(event_dict)
    
    def get_recent_events(
        self,
        session_key: str,
        limit: int = 50,
    ) -> list[EventRecord]:
        """获取最近的事件记录"""
        event_dicts = self.db_backend.list_events_by_session(session_key, limit=limit)
        events = []
        for event_dict in event_dicts:
            # 反序列化 JSON 字段（总是删除这些字段）
            if 'obs_json' in event_dict:
                event_dict['obs'] = json.loads(event_dict.pop('obs_json'))
            if 'gate_json' in event_dict:
                gate_json = event_dict.pop('gate_json')
                if gate_json:
                    event_dict['gate'] = json.loads(gate_json)
            if 'meta_json' in event_dict:
                event_dict['meta'] = json.loads(event_dict.pop('meta_json'))
            events.append(EventRecord.from_dict(event_dict))
        return events
    
    # ===== 对话轮次管理 =====
    
    def append_turn(
        self,
        session_key: str,
        input_event_id: str,
        plan: Optional[dict] = None,
        meta: Optional[dict] = None,
    ) -> TurnRecord:
        """开始新的对话轮次"""
        turn = TurnRecord(
            turn_id=f"turn_{int(time.time() * 1000)}_{input_event_id[:8]}",
            session_key=session_key,
            input_event_id=input_event_id,
            plan=plan,
            started_ts=time.time(),
            meta=meta or {},
        )
        turn_dict = turn.to_dict()
        # 序列化 JSON 字段
        if 'plan' in turn_dict and turn_dict['plan']:
            turn_dict['plan_json'] = json.dumps(turn_dict.pop('plan'))
        else:
            turn_dict.pop('plan', None)
        if 'tool_calls' in turn_dict:
            turn_dict['tool_calls_json'] = json.dumps(turn_dict.pop('tool_calls'))
        if 'tool_results' in turn_dict:
            turn_dict['tool_results_json'] = json.dumps(turn_dict.pop('tool_results'))
        if 'meta' in turn_dict:
            turn_dict['meta_json'] = json.dumps(turn_dict.pop('meta'))
        self.db_backend.save_turn_dict(turn_dict)
        logger.debug(f"Turn started: {turn.turn_id}")
        return turn
    
    def finish_turn(
        self,
        turn_id: str,
        final_output_obs_id: Optional[str] = None,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> None:
        """完成对话轮次"""
        self.db_backend.update_turn_status(turn_id, status, error)
        turn = self._get_turn_from_db(turn_id)
        if turn:
            turn.finished_ts = time.time()
            turn.final_output_obs_id = final_output_obs_id
            turn.status = status
            turn.error = error
            turn_dict = turn.to_dict()
            # 序列化 JSON 字段
            if 'plan' in turn_dict and turn_dict['plan']:
                turn_dict['plan_json'] = json.dumps(turn_dict.pop('plan'))
            else:
                turn_dict.pop('plan', None)
            if 'tool_calls' in turn_dict:
                turn_dict['tool_calls_json'] = json.dumps(turn_dict.pop('tool_calls'))
            if 'tool_results' in turn_dict:
                turn_dict['tool_results_json'] = json.dumps(turn_dict.pop('tool_results'))
            if 'meta' in turn_dict:
                turn_dict['meta_json'] = json.dumps(turn_dict.pop('meta'))
            self.db_backend.save_turn_dict(turn_dict)
        logger.debug(f"Turn finished: {turn_id}")
    
    def get_recent_turns(
        self,
        session_key: str,
        limit: int = 10,
    ) -> list[TurnRecord]:
        """获取最近的对话轮次记录"""
        turn_dicts = self.db_backend.list_turns_by_session(session_key, limit=limit)
        turns = []
        for turn_dict in turn_dicts:
            # 反序列化 JSON 字段（总是删除这些字段）
            if 'plan_json' in turn_dict:
                plan_json = turn_dict.pop('plan_json')
                if plan_json:
                    turn_dict['plan'] = json.loads(plan_json)
            if 'tool_calls_json' in turn_dict:
                turn_dict['tool_calls'] = json.loads(turn_dict.pop('tool_calls_json'))
            if 'tool_results_json' in turn_dict:
                turn_dict['tool_results'] = json.loads(turn_dict.pop('tool_results_json'))
            if 'meta_json' in turn_dict:
                turn_dict['meta'] = json.loads(turn_dict.pop('meta_json'))
            turns.append(TurnRecord.from_dict(turn_dict))
        return turns
    
    # ===== 记忆条目管理 =====
    
    def get_items(
        self,
        scope: MemoryScope,
        kind: Optional[str] = None,
    ) -> list[MemoryItem]:
        """获取指定 scope 的记忆条目"""
        return self.markdown_store.list(scope, kind)
    
    def get_item(self, scope: MemoryScope, kind: str, key: str) -> Optional[MemoryItem]:
        """获取单个记忆条目"""
        return self.markdown_store.get(scope, kind, key)
    
    def upsert_item(self, item: MemoryItem) -> None:
        """新增或更新记忆条目"""
        self.markdown_store.upsert(item)
        if self.vector_index:
            self._index_item(item)
        logger.debug(f"Item upserted: {item.scope}/{item.kind}/{item.key}")
    
    def upsert_items(self, items: list[MemoryItem]) -> None:
        """批量新增或更新记忆条目"""
        for item in items:
            self.upsert_item(item)
    
    def delete_item(self, scope: MemoryScope, kind: str, key: str) -> bool:
        """删除记忆条目"""
        result = self.markdown_store.delete(scope, kind, key)
        if self.vector_index:
            item_id = f"{scope}/{kind}/{key}"
            self.vector_index.delete(item_id)
        return result
    
    def search_items(
        self,
        query: str,
        scope: Optional[MemoryScope] = None,
        topk: int = 10,
    ) -> list[MemoryItem]:
        """搜索记忆条目"""
        if self.vector_index:
            return self._search_by_vector(query, scope, topk)
        else:
            return self.markdown_store.search_text(query, scope)[:topk]
    
    # ===== 上下文构建 =====
    
    def build_context_pack(
        self,
        session_key: str,
        user_id: Optional[str] = None,
        n_events: int = 50,
        n_turns: int = 10,
        topk_search: int = 8,
    ) -> ContextPack:
        """构建上下文包（唯一的上下文获取入口）"""
        pack = ContextPack()
        
        # 获取 Global Persona
        persona_items = self.get_items("global", kind="persona")
        pack.persona = persona_items
        
        # 获取用户画像
        if user_id:
            user_items = self.get_items("user")
            pack.user_profile = [
                item for item in user_items
                if user_id in item.key
            ]
        
        # 获取会话级记忆
        session_items = self.get_items("session")
        pack.session_items = session_items
        
        # 获取最近事件
        pack.recent_events = self.get_recent_events(session_key, limit=n_events)
        
        # 获取最近对话轮次
        pack.recent_turns = self.get_recent_turns(session_key, limit=n_turns)
        
        # 语义检索
        if pack.recent_events:
            latest_event = pack.recent_events[0]
            query_text = getattr(
                latest_event.obs.payload, "text", str(latest_event.obs)
            )
            pack.retrieved_items = self.search_items(query_text, topk=topk_search)
        
        return pack
    
    # ===== 向量索引管理 =====
    
    def reindex_all_items(self) -> int:
        """重建所有项的向量索引"""
        if not self.vector_index:
            logger.warning("Vector index not available, skipping reindex")
            return 0
        
        self.vector_index.clear()
        count = 0
        for scope in ["global", "user", "episodic", "kb"]:
            items = self.get_items(scope)
            for item in items:
                self._index_item(item)
                count += 1
        
        logger.info(f"Reindexed {count} items")
        return count
    
    # ===== 私有方法 =====
    
    def _get_turn_from_db(self, turn_id: str) -> Optional[TurnRecord]:
        """从数据库获取对话轮次"""
        turn_dict = self.db_backend.get_turn_dict(turn_id)
        if not turn_dict:
            return None
        # 反序列化 JSON 字段（总是删除这些字段）
        if 'plan_json' in turn_dict:
            plan_json = turn_dict.pop('plan_json')
            if plan_json:
                turn_dict['plan'] = json.loads(plan_json)
        if 'tool_calls_json' in turn_dict:
            turn_dict['tool_calls'] = json.loads(turn_dict.pop('tool_calls_json'))
        if 'tool_results_json' in turn_dict:
            turn_dict['tool_results'] = json.loads(turn_dict.pop('tool_results_json'))
        if 'meta_json' in turn_dict:
            turn_dict['meta'] = json.loads(turn_dict.pop('meta_json'))
        return TurnRecord.from_dict(turn_dict)
    
    def _index_item(self, item: MemoryItem) -> None:
        """为单个项建立向量索引"""
        if not self.vector_index:
            return
        
        item_id = f"{item.scope}/{item.kind}/{item.key}"
        metadata = {
            "scope": item.scope,
            "kind": item.kind,
            "key": item.key,
            "source": item.source,
        }
        
        self.vector_index.upsert(item_id, item.content, metadata)
    
    def _search_by_vector(
        self,
        query: str,
        scope: Optional[MemoryScope] = None,
        topk: int = 10,
    ) -> list[MemoryItem]:
        """使用向量搜索"""
        if not self.vector_index:
            return []
        
        filters = None
        if scope:
            filters = {"scope": scope}
        
        results = self.vector_index.query(query, topk=topk, filters=filters)
        
        # 转换为 MemoryItem
        items = []
        for result in results:
            parts = result.id.split("/", 2)
            if len(parts) == 3:
                scope_val, kind, key = parts
                item = self.get_item(scope_val, kind, key)
                if item:
                    items.append(item)
        
        return items
    
    def close(self) -> None:
        """关闭服务"""
        self.db_backend.close()
        logger.info("MemoryService closed")
