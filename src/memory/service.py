# memory/service.py
# =========================
# 记忆服务（Memory Service - 完整实现）
# =========================

from __future__ import annotations

import json
import time
import logging
import threading
import atexit
import uuid
from pathlib import Path
from collections import deque
from typing import TYPE_CHECKING, Optional, Any

from .models import EventRecord, MemoryItem, TurnRecord

if TYPE_CHECKING:
    from src.schemas.observation import Observation
    from .backends.relational import SQLAlchemyBackend
    from .backends.vector import VectorIndex, EmbeddingProvider
    from .backends.markdown_hybrid import MarkdownVaultHybrid

logger = logging.getLogger(__name__)


class MemoryService:
    """
    记忆服务（Memory Service）
    
    提供高层次的记忆管理接口，作为唯一入口。
    设计原则：Agent/Speaker 不允许直接从 bus 读取上下文。
    
    架构：L1 内存缓冲 + L2 数据库持久化
    - Event: 先进缓冲区（deque），后台线程异步写 DB
    - Turn: 直接写 DB（结构化程度更高）
    - Item: 文件系统 + 向量索引（可选）
    """
    
    def __init__(
        self,
        db_backend: SQLAlchemyBackend,
        markdown_vault: Optional[MarkdownVaultHybrid] = None,
        markdown_vault_path: str = "config",
        vector_index: Optional[VectorIndex] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        buffer_size: int = 1000,
        flush_interval_ms: int = 200,
        failed_events_max_in_memory: int = 10000,
        failed_events_spill_batch_size: int = 200,
        failed_events_dump_max_bytes: int = 50 * 1024 * 1024,
        failed_events_dump_backups: int = 3,
        failed_events_max_retries: int = 20,
    ):
        """初始化记忆服务
        
        Args:
            db_backend: 数据库后端
            markdown_vault: Markdown 配置存储（推荐使用混合 Vault）
            markdown_vault_path: Markdown 库路径（如果未提供 vault 实例）
            vector_index: 向量索引（可选）
            embedding_provider: Embedding 提供者（可选）
            buffer_size: 缓冲区大小（默认1000）
            flush_interval_ms: 后台持久化间隔（默认200ms）
            failed_events_max_in_memory: 失败事件内存上限
            failed_events_spill_batch_size: 超限时每次落盘条数
            failed_events_dump_max_bytes: 失败事件文件最大字节数
            failed_events_dump_backups: 失败事件轮转备份数量
            failed_events_max_retries: 失败事件最大重试次数
        """
        self.db_backend = db_backend
        
        # Markdown 配置存储（混合架构）
        if markdown_vault is None:
            from .backends.markdown_hybrid import MarkdownVaultHybrid
            self.markdown_vault = MarkdownVaultHybrid(
                markdown_vault_path,
                db_backend=db_backend,
            )
        else:
            self.markdown_vault = markdown_vault
        self.markdown_store = None
        
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        
        # L1: 内存缓冲层
        self._event_buffer = deque(maxlen=buffer_size)
        self._turn_buffer = deque(maxlen=100)
        self._failed_events: list[dict] = []
        self._buffer_lock = threading.RLock()  # 保护缓冲区的并发访问
        self._failed_file_lock = threading.RLock()  # 保护失败事件文件写入/轮转
        self._failed_events_max_in_memory = max(1, int(failed_events_max_in_memory))
        self._failed_events_spill_batch_size = max(1, int(failed_events_spill_batch_size))
        self._failed_events_dump_max_bytes = max(1, int(failed_events_dump_max_bytes))
        self._failed_events_dump_backups = max(0, int(failed_events_dump_backups))
        self._failed_events_max_retries = max(1, int(failed_events_max_retries))
        self._failed_events_file = (
            Path(getattr(self.markdown_vault, "vault_root", ".")) / "failed_events.jsonl"
        )
        self._dead_letter_file = (
            Path(getattr(self.markdown_vault, "vault_root", ".")) / "failed_events.dead.jsonl"
        )
        
        self.db_backend.initialize()
        self._load_failed_events_from_disk()
        
        # 后台持久化线程控制
        self._flush_interval = flush_interval_ms / 1000.0  # 转换为秒
        self._stop_flushing = threading.Event()
        self._flush_thread = threading.Thread(
            target=self._background_flush,
            daemon=True,
            name="MemoryService-Flush-Thread",
        )
        self._flush_thread.start()
        self._closed = False
        
        # 注册程序退出处理：确保所有缓冲区数据都被持久化
        atexit.register(self.close)
        logger.info("MemoryService initialized (buffer_size=%d, flush_interval=%dms)",
                    buffer_size, flush_interval_ms)
    
    # ===== 事件管理 =====
    
    def append_event(
        self,
        obs: Observation,
        session_key: str,
        gate_result: Optional[dict] = None,
        meta: Optional[dict] = None,
    ) -> EventRecord:
        """记录事件到缓冲区（L1)
        
        事件先进入内存缓冲区，后台线程定期将其刷到数据库（L2）。
        这样可以减少磁盘 I/O，提高吞吐量。
        """
        event = EventRecord(
            event_id=f"evt_{int(time.time() * 1000)}_{uuid.uuid4().hex[:12]}_{obs.obs_id[:8]}",
            ts=time.time(),
            session_key=session_key,
            obs=obs,
            gate=gate_result,
            meta=meta or {},
        )
        
        # 序列化成 dict 格式（为持久化做准备）
        event_dict = event.to_dict()
        event_dict['obs_json'] = json.dumps(event_dict.pop('obs'))
        if 'gate' in event_dict and event_dict['gate']:
            event_dict['gate_json'] = json.dumps(event_dict.pop('gate'))
        else:
            event_dict.pop('gate', None)
        if 'meta' in event_dict:
            event_dict['meta_json'] = json.dumps(event_dict.pop('meta'))
        
        # 写入 L1 缓冲区（线程安全）
        with self._buffer_lock:
            self._event_buffer.append(event_dict)
        
        logger.debug(f"Event buffered: {event.event_id} (buffer_size={len(self._event_buffer)})")
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
        """获取最近的事件记录（L1+L2 查询策略）
        
        1. 先从 L1 内存缓冲区查询（最新的、未持久化的事件）
        2. 如果缓冲区事件不足，再从 L2 数据库补充
        
        这样可以保证获得最新的事件，同时减少数据库查询频率。
        """
        events = []
        
        # L1: 从内存缓冲区查询（时间序列倒序）
        with self._buffer_lock:
            buffered_events = list(self._event_buffer)  # 浅拷贝
        
        # 按 session_key 过滤并倒序（最新在前）
        buffered_events = [
            e for e in reversed(buffered_events)
            if e.get('session_key') == session_key
        ]
        
        # 添加 L1 事件
        for event_dict in buffered_events[:limit]:
            events.append(self._deserialize_event(event_dict))
        
        # 如果 L1 事件足够，直接返回
        if len(events) >= limit:
            return events[:limit]
        
        # L2: 从数据库补充
        remaining = limit - len(events)
        db_event_dicts = self.db_backend.list_events_by_session(
            session_key, limit=remaining
        )
        
        for event_dict in db_event_dicts:
            events.append(self._deserialize_event(event_dict))
        
        # 去重：L1/L2 可能在并发 flush 场景下出现同一事件重复
        deduped_events: list[EventRecord] = []
        seen_event_ids: set[str] = set()
        for event in events:
            if event.event_id in seen_event_ids:
                continue
            seen_event_ids.add(event.event_id)
            deduped_events.append(event)
        
        return deduped_events[:limit]
    
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
            turn_id=f"turn_{int(time.time() * 1000)}_{uuid.uuid4().hex[:12]}_{input_event_id[:8]}",
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
        self.db_backend.update_turn_status(
            turn_id,
            status,
            error,
            final_output_obs_id=final_output_obs_id,
            finished_ts=time.time()
        )
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
            # 反序列化 JSON 字段 - 无条件删除_json键
            if 'plan_json' in turn_dict:
                if turn_dict['plan_json']:
                    turn_dict['plan'] = json.loads(turn_dict['plan_json'])
                del turn_dict['plan_json']
            if 'tool_calls_json' in turn_dict:
                if turn_dict['tool_calls_json']:
                    turn_dict['tool_calls'] = json.loads(turn_dict['tool_calls_json'])
                del turn_dict['tool_calls_json']
            if 'tool_results_json' in turn_dict:
                if turn_dict['tool_results_json']:
                    turn_dict['tool_results'] = json.loads(turn_dict['tool_results_json'])
                del turn_dict['tool_results_json']
            if 'meta_json' in turn_dict:
                if turn_dict['meta_json']:
                    turn_dict['meta'] = json.loads(turn_dict['meta_json'])
                del turn_dict['meta_json']
            turns.append(TurnRecord.from_dict(turn_dict))
        return turns
    
    # ===== 记忆条目管理（兼容旧版 API）=====
    
    def get_items(
        self,
        scope: str,
        kind: Optional[str] = None,
    ) -> list[MemoryItem]:
        """获取指定 scope 的记忆条目（仅兼容旧版）"""
        if self.markdown_store is None:
            logger.warning("get_items() is deprecated with MarkdownVaultHybrid. Use get_config() instead.")
            return []
        return self.markdown_store.list(scope, kind)
    
    def get_item(self, scope: str, kind: str, key: str) -> Optional[MemoryItem]:
        """获取单个记忆条目（仅兼容旧版）"""
        if self.markdown_store is None:
            logger.warning("get_item() is deprecated with MarkdownVaultHybrid. Use get_config() instead.")
            return None
        return self.markdown_store.get(scope, kind, key)
    
    def upsert_item(self, item: MemoryItem) -> None:
        """新增或更新记忆条目（仅兼容旧版）"""
        if self.markdown_store is None:
            logger.warning("upsert_item() is deprecated with MarkdownVaultHybrid. Use upsert_config() instead.")
            return
        self.markdown_store.upsert(item)
        if self.vector_index and self.embedding_provider:
            self._index_item(item)
        logger.debug(f"Item upserted: {item.scope}/{item.kind}/{item.key}")
    
    def upsert_items(self, items: list[MemoryItem]) -> None:
        """批量新增或更新记忆条目（仅兼容旧版）"""
        for item in items:
            self.upsert_item(item)
    
    def delete_item(self, scope: str, kind: str, key: str) -> bool:
        """删除记忆条目（仅兼容旧版）"""
        if self.markdown_store is None:
            logger.warning("delete_item() is deprecated with MarkdownVaultHybrid.")
            return False
        result = self.markdown_store.delete(scope, kind, key)
        if self.vector_index:
            item_id = f"{scope}/{kind}/{key}"
            self.vector_index.delete(item_id)
        return result
    
    def search_items(
        self,
        query: str,
        scope: Optional[str] = None,
        topk: int = 10,
    ) -> list[MemoryItem]:
        """搜索记忆条目（仅兼容旧版）"""
        if self.markdown_store is None:
            logger.warning("search_items() is deprecated with MarkdownVaultHybrid.")
            return []
        if self.vector_index and self.embedding_provider:
            return self._search_by_vector(query, scope, topk)
        else:
            return self.markdown_store.search_text(query, scope)[:topk]
    
    # ===== Markdown 配置管理（新版 API - 推荐）=====
    
    def get_system_prompt(self) -> str:
        """获取系统 prompt（从 Markdown Vault）"""
        return self.markdown_vault.get_system_config() if self.markdown_vault else ""
    
    def get_user_profile(self, user_id: str) -> str:
        """获取用户配置（从 Markdown Vault）"""
        if not self.markdown_vault:
            return ""
        return self.markdown_vault.get_user_config(user_id)
    
    def upsert_system_prompt(self, content: str, metadata: Optional[dict] = None) -> None:
        """更新系统 prompt"""
        if not self.markdown_vault:
            logger.warning("upsert_system_prompt() requires MarkdownVaultHybrid")
            return
        self.markdown_vault.upsert_config("system", content, metadata)
    
    def upsert_user_profile(self, user_id: str, content: str, metadata: Optional[dict] = None) -> None:
        """更新用户配置"""
        if not self.markdown_vault:
            logger.warning("upsert_user_profile() requires MarkdownVaultHybrid")
            return
        self.markdown_vault.upsert_config(f"user:{user_id}", content, metadata)
    
    def get_config(self, key: str) -> Optional[str]:
        """获取配置（通用方法）"""
        if self.markdown_vault:
            return self.markdown_vault.get_config(key)
        else:
            logger.warning("get_config() requires MarkdownVaultHybrid")
            return None
    
    def upsert_config(self, key: str, content: str, metadata: Optional[dict] = None) -> None:
        """更新配置（通用方法）"""
        if self.markdown_vault:
            self.markdown_vault.upsert_config(key, content, metadata)
        else:
            logger.warning("upsert_config() requires MarkdownVaultHybrid")
    
    # ===== 向量索引管理 =====
    
    def reindex_all_items(self) -> int:
        """重建所有项的向量索引"""
        if not self.vector_index or not self.embedding_provider:
            logger.warning("Vector index not available, skipping reindex")
            return 0
        if self.markdown_store is None:
            logger.warning(
                "reindex_all_items() is not available until legacy store or future vectorization is enabled"
            )
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
    
    def _deserialize_event(self, event_dict: dict) -> EventRecord:
        """反序列化事件 dict 为 EventRecord
        
        注意：不会修改传入的 event_dict
        """
        event_dict = dict(event_dict)
        # 反序列化 JSON 字段
        if 'obs_json' in event_dict:
            event_dict['obs'] = json.loads(event_dict.pop('obs_json'))
        if 'gate_json' in event_dict:
            gate_json = event_dict.pop('gate_json')
            if gate_json:
                event_dict['gate'] = json.loads(gate_json)
        if 'meta_json' in event_dict:
            event_dict['meta'] = json.loads(event_dict.pop('meta_json'))
        return EventRecord.from_dict(event_dict)
    
    def _background_flush(self) -> None:
        """后台线程：定期将缓冲区事件持久化到数据库"""
        logger.debug("Background flush thread started")
        try:
            while not self._stop_flushing.wait(self._flush_interval):
                self._flush_event_buffer()
                self._retry_failed_events()
        finally:
            logger.debug("Background flush thread stopped")
    
    def _flush_event_buffer(self) -> None:
        """将事件缓冲区内的所有事件持久化到数据库"""
        with self._buffer_lock:
            if not self._event_buffer:
                return  # 缓冲区为空，无需刷新
            
            # 取出所有对象并清空缓冲区
            events_to_flush = list(self._event_buffer)
            self._event_buffer.clear()
        
        # 写入数据库（在锁外进行，避免长时间持锁）
        for event_dict in events_to_flush:
            try:
                self.db_backend.save_event_dict(event_dict)
            except Exception as e:
                logger.error(f"Failed to flush event {event_dict.get('event_id')}: {e}")
                self._enqueue_failed_event(
                    {
                        "event_dict": event_dict,
                        "error": str(e),
                        "failed_at": time.time(),
                        "retries": 1,
                    }
                )
        
        if events_to_flush:
            logger.debug(f"Flushed {len(events_to_flush)} events to database")

    def _retry_failed_events(self) -> int:
        """重试失败事件持久化，返回本轮成功数量。"""
        with self._buffer_lock:
            if not self._failed_events:
                return 0
            failed_batch = list(self._failed_events)
            self._failed_events.clear()
        
        recovered = 0
        still_failed: list[dict] = []
        dead_letters: list[dict] = []
        for record in failed_batch:
            event_dict = record.get("event_dict")
            if not isinstance(event_dict, dict):
                continue
            try:
                self.db_backend.save_event_dict(event_dict)
                recovered += 1
            except Exception as e:
                retries = int(record.get("retries", 0)) + 1
                record["error"] = str(e)
                record["failed_at"] = time.time()
                record["retries"] = retries
                if retries >= self._failed_events_max_retries:
                    dead_letters.append(record)
                else:
                    still_failed.append(record)
        
        if still_failed:
            for record in still_failed:
                self._enqueue_failed_event(record)
        if dead_letters:
            self._append_records_to_file(dead_letters, self._dead_letter_file)
            logger.error(
                "Moved %d failed events to dead-letter file after max retries (%d)",
                len(dead_letters),
                self._failed_events_max_retries,
            )
        
        if recovered:
            logger.info("Recovered %d previously failed events", recovered)
        return recovered

    def _load_failed_events_from_disk(self) -> None:
        """加载上次退出时落盘的失败事件。"""
        loaded = 0
        files_to_load = self._get_dump_files_in_load_order(self._failed_events_file)
        if not files_to_load:
            return
        loaded_records: list[dict] = []
        try:
            for dump_file in files_to_load:
                with dump_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        event_dict = record.get("event_dict")
                        if isinstance(event_dict, dict):
                            loaded_records.append(
                                {
                                    "event_dict": event_dict,
                                    "error": record.get("error", "loaded_from_disk"),
                                    "failed_at": float(record.get("failed_at", time.time())),
                                    "retries": int(record.get("retries", 0)),
                                }
                            )
                            loaded += 1
                dump_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Failed to load failed events dump: %s", e)
            return

        overflow_records: list[dict] = []
        if loaded_records:
            with self._buffer_lock:
                self._failed_events.extend(loaded_records)
                overflow = len(self._failed_events) - self._failed_events_max_in_memory
                if overflow > 0:
                    overflow_records = self._failed_events[:overflow]
                    del self._failed_events[:overflow]
        if overflow_records:
            self._append_records_to_file(overflow_records, self._failed_events_file)
            logger.warning(
                "Failed-event queue warm-load overflow: spilled %d records to %s",
                len(overflow_records),
                self._failed_events_file,
            )
        if loaded:
            logger.warning("Loaded %d failed events from %s", loaded, self._failed_events_file)

    def _persist_failed_events_to_disk(self) -> None:
        """将失败事件落盘，避免进程退出后数据丢失。"""
        with self._buffer_lock:
            records = list(self._failed_events)
        if not records:
            return
        self._append_records_to_file(records, self._failed_events_file)
        logger.warning(
            "Persisted %d failed events to %s",
            len(records),
            self._failed_events_file,
        )

    def _enqueue_failed_event(self, record: dict[str, Any]) -> None:
        """将失败事件加入内存队列；超限则分批落盘。"""
        overflow_records: list[dict] = []
        with self._buffer_lock:
            self._failed_events.append(record)
            overflow = len(self._failed_events) - self._failed_events_max_in_memory
            if overflow > 0:
                spill_count = min(
                    len(self._failed_events),
                    max(overflow, self._failed_events_spill_batch_size),
                )
                overflow_records = self._failed_events[:spill_count]
                del self._failed_events[:spill_count]
        if overflow_records:
            self._append_records_to_file(overflow_records, self._failed_events_file)
            logger.warning(
                "Failed-event queue overflow: spilled %d records to %s",
                len(overflow_records),
                self._failed_events_file,
            )

    def _append_records_to_file(self, records: list[dict], file_path: Path) -> None:
        """追加记录到指定 dump 文件，必要时执行轮转。"""
        if not records:
            return
        lines = [json.dumps(record, ensure_ascii=False) + "\n" for record in records]
        incoming_bytes = len("".join(lines).encode("utf-8"))
        with self._failed_file_lock:
            self._rotate_dump_file_if_needed(file_path, incoming_bytes)
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with file_path.open("a", encoding="utf-8") as f:
                    for line in lines:
                        f.write(line)
            except Exception as e:
                logger.error("Failed to append failed-event records to %s: %s", file_path, e)

    def _rotate_dump_file_if_needed(self, file_path: Path, incoming_bytes: int) -> None:
        """当文件超出阈值时执行轮转。"""
        current_size = file_path.stat().st_size if file_path.exists() else 0
        if current_size + incoming_bytes <= self._failed_events_dump_max_bytes:
            return
        try:
            if self._failed_events_dump_backups <= 0:
                file_path.unlink(missing_ok=True)
                return

            oldest_backup = self._rotated_dump_path(file_path, self._failed_events_dump_backups)
            oldest_backup.unlink(missing_ok=True)
            for idx in range(self._failed_events_dump_backups - 1, 0, -1):
                src = self._rotated_dump_path(file_path, idx)
                dst = self._rotated_dump_path(file_path, idx + 1)
                if src.exists():
                    src.replace(dst)
            if file_path.exists():
                file_path.replace(self._rotated_dump_path(file_path, 1))
        except Exception as e:
            logger.error("Failed to rotate dump file %s: %s", file_path, e)

    @staticmethod
    def _rotated_dump_path(base_file: Path, idx: int) -> Path:
        return Path(f"{base_file}.{idx}")

    def _get_dump_files_in_load_order(self, base_file: Path) -> list[Path]:
        """返回需加载的 dump 文件列表（按从旧到新顺序）。"""
        files: list[Path] = []
        for idx in range(self._failed_events_dump_backups, 0, -1):
            p = self._rotated_dump_path(base_file, idx)
            if p.exists():
                files.append(p)
        if base_file.exists():
            files.append(base_file)
        return files
    
    def _get_turn_from_db(self, turn_id: str) -> Optional[TurnRecord]:
        """从数据库获取对话轮次"""
        turn_dict = self.db_backend.get_turn_dict(turn_id)
        if not turn_dict:
            return None
        # 反序列化 JSON 字段 - 无条件删除_json键
        if 'plan_json' in turn_dict:
            if turn_dict['plan_json']:
                turn_dict['plan'] = json.loads(turn_dict['plan_json'])
            del turn_dict['plan_json']
        if 'tool_calls_json' in turn_dict:
            if turn_dict['tool_calls_json']:
                turn_dict['tool_calls'] = json.loads(turn_dict['tool_calls_json'])
            del turn_dict['tool_calls_json']
        if 'tool_results_json' in turn_dict:
            if turn_dict['tool_results_json']:
                turn_dict['tool_results'] = json.loads(turn_dict['tool_results_json'])
            del turn_dict['tool_results_json']
        if 'meta_json' in turn_dict:
            if turn_dict['meta_json']:
                turn_dict['meta'] = json.loads(turn_dict['meta_json'])
            del turn_dict['meta_json']
        return TurnRecord.from_dict(turn_dict)
    
    def _index_item(self, item: MemoryItem) -> None:
        """为单个项建立向量索引"""
        if not self.vector_index or not self.embedding_provider:
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
        scope: Optional[str] = None,
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
        """关闭服务，确保所有缓冲数据都被持久化"""
        if self._closed:
            return
        self._closed = True
        if self._flush_thread and self._flush_thread.is_alive():
            # 停止后台线程
            self._stop_flushing.set()
            self._flush_thread.join(timeout=5)  # 等待最多5秒
            
            # 最后一次手动刷新，确保所有缓冲区数据都被写入
            self._flush_event_buffer()
            self._retry_failed_events()
            self._retry_failed_events()
            
            # 准确反馈状态
            if self._failed_events:
                self._persist_failed_events_to_disk()
                logger.warning(
                    f"{len(self._failed_events)} events failed to persist "
                    f"(details dumped to {self._failed_events_file})"
                )
            else:
                logger.info("All buffered events flushed to database")
        
        self.db_backend.close()
        logger.info("MemoryService closed")
