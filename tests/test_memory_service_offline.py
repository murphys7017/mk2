# tests/test_memory_service_offline.py
# =========================
# Memory 子系统离线测试
# 不需要外部服务（MySQL、向量库等）
# =========================

import pytest
import tempfile
import time
import json
from pathlib import Path

from src.schemas.observation import make_message_observation
from src.memory.models import EventRecord, TurnRecord
from src.memory.config import MemoryConfigProvider
from src.memory.backends.relational import SQLAlchemyBackend
from src.memory.backends.vector import InMemoryVectorIndex, DeterministicEmbeddingProvider
from src.memory.service import MemoryService
from src.memory.backends.markdown_hybrid import MarkdownVaultHybrid


def _load_test_dsn() -> str:
    config = MemoryConfigProvider(Path("config/memory.yaml")).snapshot()
    return config.database.dsn


@pytest.fixture
def temp_vault():
    """创建临时 Vault 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def memory_service(temp_vault):
    """创建内存 MemoryService"""
    from src.memory.backends.relational import Base
    
    db_backend = SQLAlchemyBackend(_load_test_dsn())
    
    # 清理数据库：删除所有表并重新创建（确保测试隔离）
    Base.metadata.drop_all(db_backend.engine)
    Base.metadata.create_all(db_backend.engine)
    
    vector_index = InMemoryVectorIndex(DeterministicEmbeddingProvider())
    embedding_provider = DeterministicEmbeddingProvider()
    markdown_vault = MarkdownVaultHybrid(temp_vault, db_backend=db_backend)
    
    service = MemoryService(
        db_backend=db_backend,
        markdown_vault=markdown_vault,
        vector_index=vector_index,
        embedding_provider=embedding_provider,
    )
    
    yield service
    service.close()


class TestEventRecord:
    """EventRecord 测试"""
    
    def test_event_record_creation(self):
        """测试 EventRecord 创建"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        
        event = EventRecord(
            event_id="evt_1",
            ts=time.time(),
            session_key="session_1",
            obs=obs,
        )
        
        assert event.event_id == "evt_1"
        assert event.session_key == "session_1"
        assert event.obs.payload.text == "Hello"
    
    def test_event_record_serialization(self):
        """测试 EventRecord 序列化"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        
        event = EventRecord(
            event_id="evt_1",
            ts=time.time(),
            session_key="session_1",
            obs=obs,
        )
        
        # 转为 dict
        event_dict = event.to_dict()
        assert event_dict["event_id"] == "evt_1"
        assert event_dict["obs"]["payload"]["text"] == "Hello"
        
        # 从 dict 还原
        restored = EventRecord.from_dict(event_dict)
        assert restored.event_id == event.event_id
        assert restored.obs.payload.text == event.obs.payload.text


class TestMarkdownVaultHybrid:
    """MarkdownVaultHybrid 测试"""
    
    def test_upsert_and_get_config(self, temp_vault):
        """测试配置文件新增和获取"""
        vault = MarkdownVaultHybrid(temp_vault)
        
        vault.upsert_config(
            key="system",
            content="I am a helpful assistant",
            frontmatter={"version": "1.0"},
        )
        
        retrieved = vault.get_system_config()
        assert retrieved == "I am a helpful assistant"
    
    def test_upsert_and_get_knowledge(self, temp_vault):
        """测试知识条目新增和获取"""
        vault = MarkdownVaultHybrid(temp_vault)
        
        vault.upsert_knowledge(
            key="facts/python",
            content="Python is a programming language",
            frontmatter={"topic": "python"},
        )
        
        retrieved = vault.get_knowledge("facts/python")
        assert retrieved == "Python is a programming language"
    
    def test_list_knowledge(self, temp_vault):
        """测试列出知识条目"""
        vault = MarkdownVaultHybrid(temp_vault)
        
        for i in range(3):
            vault.upsert_knowledge(
                key=f"facts/fact_{i}",
                content=f"Fact {i}",
            )
        
        items = vault.list_knowledge("facts")
        assert len(items) == 3

    def test_reload_prunes_stale_metadata(self, temp_vault):
        """删除文件后 reload 应清理残留 metadata"""
        vault = MarkdownVaultHybrid(temp_vault)
        vault.upsert_config("system", "test")

        system_path = Path(temp_vault) / "md" / "system.md"
        assert system_path.exists()
        system_path.unlink()

        vault.reload()
        stale_exists = any(Path(k).as_posix() == "md/system.md" for k in vault.metadata.keys())
        assert stale_exists is False

    def test_delete_knowledge_syncs_db(self, temp_vault):
        """删除知识条目应同步删除 DB 记录"""
        from src.memory.backends.relational import Base
        
        db_backend = SQLAlchemyBackend(_load_test_dsn())
        
        # 清理数据库（确保测试隔离）
        Base.metadata.drop_all(db_backend.engine)
        Base.metadata.create_all(db_backend.engine)
        
        db_backend.initialize()
        vault = MarkdownVaultHybrid(temp_vault, db_backend=db_backend)
        vault.upsert_knowledge("facts/test", "hello")

        assert db_backend.get_knowledge_dict("facts/test") is not None
        assert vault.delete_knowledge("facts/test") is True
        assert db_backend.get_knowledge_dict("facts/test") is None


class TestMemoryService:
    """MemoryService 集成测试"""
    
    def test_append_event(self, memory_service):
        """测试添加事件"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        
        event = memory_service.append_event(obs, "session_1")
        assert event.event_id is not None
        assert event.session_key == "session_1"
    
    def test_get_recent_events(self, memory_service):
        """测试获取最近事件"""
        obs1 = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Message 1",
        )
        
        obs2 = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Message 2",
        )
        
        memory_service.append_event(obs1, "session_1")
        time.sleep(0.01)  # 确保时间戳不同
        memory_service.append_event(obs2, "session_1")
        
        events = memory_service.get_recent_events("session_1", limit=10)
        assert len(events) == 2
        # 应该按时间倒序
        assert events[0].obs.payload.text == "Message 2"
        assert events[1].obs.payload.text == "Message 1"
    
    def test_append_turn(self, memory_service):
        """测试添加对话轮次"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        
        event = memory_service.append_event(obs, "session_1")
        
        turn = memory_service.append_turn(
            session_key="session_1",
            input_event_id=event.event_id,
            plan={"intent": "greet"},
        )
        
        assert turn.turn_id is not None
        assert turn.input_event_id == event.event_id
        assert turn.plan["intent"] == "greet"
    
    def test_get_system_prompt(self, memory_service):
        """测试获取系统 prompt"""
        memory_service.upsert_system_prompt("You are a helpful assistant")
        prompt = memory_service.get_system_prompt()
        assert prompt == "You are a helpful assistant"

    def test_finish_turn_without_plan(self, memory_service):
        """plan=None 时 finish_turn/get_recent_turns 不应崩溃"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        event = memory_service.append_event(obs, "session_1")
        turn = memory_service.append_turn(
            session_key="session_1",
            input_event_id=event.event_id,
            plan=None,
        )
        memory_service.finish_turn(turn.turn_id, status="ok")
        turns = memory_service.get_recent_turns("session_1", limit=10)
        assert len(turns) >= 1

    def test_finish_turn_can_clear_error(self, memory_service):
        """error=None 应清空历史错误信息"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        event = memory_service.append_event(obs, "session_1")
        turn = memory_service.append_turn(
            session_key="session_1",
            input_event_id=event.event_id,
            plan={"intent": "demo"},
        )
        memory_service.finish_turn(turn.turn_id, status="error", error="boom")
        memory_service.finish_turn(turn.turn_id, status="ok", error=None)
        turn_dict = memory_service.db_backend.get_turn_dict(turn.turn_id)
        assert turn_dict["status"] == "ok"
        assert turn_dict["error"] is None

    def test_turn_id_uniqueness(self, memory_service):
        """高频创建 turn_id 不应碰撞"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        event = memory_service.append_event(obs, "session_1")
        turn_ids = [
            memory_service.append_turn("session_1", event.event_id).turn_id
            for _ in range(50)
        ]
        assert len(set(turn_ids)) == len(turn_ids)

    def test_recent_events_dedup_between_l1_l2(self, memory_service):
        """并发 flush 重叠场景应去重"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        event = memory_service.append_event(obs, "session_1")

        original = memory_service.db_backend.list_events_by_session

        def hooked(session_key: str, limit: int = 100, offset: int = 0):
            memory_service._flush_event_buffer()
            return original(session_key, limit=limit, offset=offset)

        memory_service.db_backend.list_events_by_session = hooked
        events = memory_service.get_recent_events("session_1", limit=10)
        event_ids = [e.event_id for e in events]
        assert event.event_id in event_ids
        assert len(event_ids) == len(set(event_ids))

    def test_failed_events_retry(self, memory_service):
        """失败事件应可通过重试恢复"""
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Hello",
        )
        event = memory_service.append_event(obs, "session_1")

        original = memory_service.db_backend.save_event_dict
        calls = {"n": 0}

        def flaky(event_dict: dict):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return original(event_dict)

        memory_service.db_backend.save_event_dict = flaky
        memory_service._flush_event_buffer()
        assert len(memory_service._failed_events) == 1
        memory_service._retry_failed_events()
        assert len(memory_service._failed_events) == 0
        assert memory_service.get_event(event.event_id) is not None

    def test_failed_events_queue_overflow_spills_to_disk(self, temp_vault):
        """失败事件超过内存上限时应分批落盘。"""
        db_backend = SQLAlchemyBackend("sqlite:///:memory:")
        markdown_vault = MarkdownVaultHybrid(temp_vault, db_backend=db_backend)
        service = MemoryService(
            db_backend=db_backend,
            markdown_vault=markdown_vault,
            failed_events_max_in_memory=3,
            failed_events_spill_batch_size=2,
            failed_events_dump_max_bytes=1024 * 1024,
            failed_events_dump_backups=1,
        )
        try:
            for i in range(5):
                service._enqueue_failed_event(
                    {
                        "event_dict": {"event_id": f"evt_{i}", "obs_json": "{}"},
                        "error": "boom",
                        "failed_at": time.time(),
                        "retries": 1,
                    }
                )

            assert len(service._failed_events) == 3
            dump_file = Path(temp_vault) / "failed_events.jsonl"
            assert dump_file.exists()
            lines = [ln for ln in dump_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            assert len(lines) == 2
        finally:
            service.close()

    def test_failed_events_dump_rotation_keeps_backup_limit(self, temp_vault):
        """失败事件 dump 文件应按上限轮转且不超过备份数。"""
        db_backend = SQLAlchemyBackend("sqlite:///:memory:")
        markdown_vault = MarkdownVaultHybrid(temp_vault, db_backend=db_backend)
        service = MemoryService(
            db_backend=db_backend,
            markdown_vault=markdown_vault,
            failed_events_dump_max_bytes=120,
            failed_events_dump_backups=2,
        )
        try:
            payload = "x" * 180
            for i in range(4):
                service._append_records_to_file(
                    [{"event_dict": {"event_id": f"evt_{i}", "payload": payload}, "retries": 1}],
                    service._failed_events_file,
                )

            assert service._failed_events_file.exists()
            assert service._rotated_dump_path(service._failed_events_file, 1).exists()
            assert service._rotated_dump_path(service._failed_events_file, 2).exists()
            assert not service._rotated_dump_path(service._failed_events_file, 3).exists()
        finally:
            service.close()

    def test_failed_events_persist_and_reload_from_disk(self, temp_vault):
        """失败事件应可落盘并在下次启动时重新加载。"""
        db_backend_1 = SQLAlchemyBackend("sqlite:///:memory:")
        vault_1 = MarkdownVaultHybrid(temp_vault, db_backend=db_backend_1)
        service_1 = MemoryService(
            db_backend=db_backend_1,
            markdown_vault=vault_1,
            flush_interval_ms=60000,
        )
        try:
            service_1._enqueue_failed_event(
                {
                    "event_dict": {
                        "event_id": "evt_reload_1",
                        "session_key": "s1",
                        "ts": time.time(),
                        "obs_json": "{}",
                        "meta_json": "{}",
                    },
                    "error": "persist_me",
                    "failed_at": time.time(),
                    "retries": 0,
                }
            )
            service_1._persist_failed_events_to_disk()
            dump_file = Path(temp_vault) / "failed_events.jsonl"
            assert dump_file.exists()
            assert dump_file.read_text(encoding="utf-8").strip()
        finally:
            service_1.close()

        db_backend_2 = SQLAlchemyBackend("sqlite:///:memory:")
        vault_2 = MarkdownVaultHybrid(temp_vault, db_backend=db_backend_2)
        service_2 = MemoryService(
            db_backend=db_backend_2,
            markdown_vault=vault_2,
            flush_interval_ms=60000,
        )
        try:
            assert len(service_2._failed_events) >= 1
            dump_file = Path(temp_vault) / "failed_events.jsonl"
            assert not dump_file.exists()
        finally:
            service_2.close()

    def test_failed_events_move_to_dead_letter_after_max_retries(self, temp_vault):
        """超过最大重试次数的失败事件应进入 dead-letter 文件。"""
        db_backend = SQLAlchemyBackend("sqlite:///:memory:")
        markdown_vault = MarkdownVaultHybrid(temp_vault, db_backend=db_backend)
        service = MemoryService(
            db_backend=db_backend,
            markdown_vault=markdown_vault,
            failed_events_max_retries=2,
            flush_interval_ms=60000,
        )
        try:
            def always_fail(_event_dict: dict):
                raise RuntimeError("db_down")

            service.db_backend.save_event_dict = always_fail
            service._enqueue_failed_event(
                {
                    "event_dict": {
                        "event_id": "evt_dead_1",
                        "session_key": "s1",
                        "ts": time.time(),
                        "obs_json": "{}",
                        "meta_json": "{}",
                    },
                    "error": "init",
                    "failed_at": time.time(),
                    "retries": 0,
                }
            )

            service._retry_failed_events()
            assert len(service._failed_events) == 1

            service._retry_failed_events()
            assert len(service._failed_events) == 0

            dead_file = Path(temp_vault) / "failed_events.dead.jsonl"
            assert dead_file.exists()
            lines = [ln for ln in dead_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            assert len(lines) == 1
            dead_record = json.loads(lines[0])
            assert dead_record.get("retries") >= 2
        finally:
            service.close()


class TestVectorIndex:
    """向量索引测试"""
    
    def test_in_memory_vector_index(self):
        """测试内存向量索引"""
        embedding = DeterministicEmbeddingProvider(dim=64)
        index = InMemoryVectorIndex(embedding)
        
        # Upsert
        index.upsert("id1", "Python programming", {"scope": "kb"})
        index.upsert("id2", "JavaScript development", {"scope": "kb"})
        index.upsert("id3", "Database management", {"scope": "kb"})
        
        # Query
        results = index.query("Python", topk=2)
        assert len(results) <= 2
        assert any(r.id == "id1" for r in results)
        
        # Delete
        success = index.delete("id1")
        assert success
        
        # Query again
        results = index.query("Python", topk=2)
        assert not any(r.id == "id1" for r in results)


if __name__ == "__main__":
    pytest.main([__file__,  "-v"])
