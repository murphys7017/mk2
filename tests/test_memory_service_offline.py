# tests/test_memory_service_offline.py
# =========================
# Memory 子系统离线测试
# 不需要外部服务（MySQL、向量库等）
# =========================

import pytest
import tempfile
import time
from pathlib import Path

from src.schemas.observation import make_message_observation
from src.memory.models import EventRecord, TurnRecord, MemoryItem, ContextPack
from src.memory.backends.relational import SQLAlchemyBackend
from src.memory.backends.vector import InMemoryVectorIndex, DeterministicEmbeddingProvider
from src.memory.service import MemoryService
from src.memory.vault import MarkdownItemStore


@pytest.fixture
def temp_vault():
    """创建临时 Vault 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def memory_service(temp_vault):
    """创建内存 MemoryService"""
    db_backend = SQLAlchemyBackend("sqlite:///:memory:")
    vector_index = InMemoryVectorIndex(DeterministicEmbeddingProvider())
    embedding_provider = DeterministicEmbeddingProvider()
    
    service = MemoryService(
        db_backend=db_backend,
        markdown_vault_path=temp_vault,
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


class TestMemoryItemStore:
    """MemoryItemStore 测试"""
    
    def test_upsert_and_get(self, temp_vault):
        """测试新增和获取"""
        store = MarkdownItemStore(temp_vault)
        
        item = MemoryItem(
            scope="global",
            kind="persona",
            key="assistant",
            content="I am a helpful assistant",
            source="system",
        )
        
        store.upsert(item)
        
        retrieved = store.get("global", "persona", "assistant")
        assert retrieved is not None
        assert retrieved.content == "I am a helpful assistant"
    
    def test_list_items(self, temp_vault):
        """测试列出项"""
        store = MarkdownItemStore(temp_vault)
        
        for i in range(3):
            item = MemoryItem(
                scope="global",
                kind="knowledge",
                key=f"fact_{i}",
                content=f"Fact {i}",
                source="system",
            )
            store.upsert(item)
        
        items = store.list("global")
        assert len(items) == 3
    
    def test_search_text(self, temp_vault):
        """测试文本搜索"""
        store = MarkdownItemStore(temp_vault)
        
        item1 = MemoryItem(
            scope="global",
            kind="knowledge",
            key="fact_1",
            content="Python is a programming language",
            source="system",
        )
        
        item2 = MemoryItem(
            scope="global",
            kind="knowledge",
            key="fact_2",
            content="JavaScript is used for web development",
            source="system",
        )
        
        store.upsert(item1)
        store.upsert(item2)
        
        results = store.search_text("programming")
        assert len(results) == 1
        assert results[0].key == "fact_1"


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
    
    def test_upsert_item(self, memory_service):
        """测试新增记忆项"""
        item = MemoryItem(
            scope="global",
            kind="persona",
            key="assistant_role",
            content="I am a helpful AI assistant",
            source="system",
            confidence=1.0,
        )
        
        memory_service.upsert_item(item)
        
        retrieved = memory_service.get_item("global", "persona", "assistant_role")
        assert retrieved is not None
        assert retrieved.content == "I am a helpful AI assistant"
    
    def test_build_context_pack(self, memory_service):
        """测试构建上下文包"""
        # 添加 persona
        persona = MemoryItem(
            scope="global",
            kind="persona",
            key="assistant_role",
            content="I am a helpful AI assistant",
            source="system",
        )
        memory_service.upsert_item(persona)
        
        # 添加事件
        obs = make_message_observation(
            source_name="test",
            session_key="session_1",
            actor_id="user_1",
            text="Tell me about Python",
        )
        memory_service.append_event(obs, "session_1")
        
        # 构建上下文
        pack = memory_service.build_context_pack("session_1", user_id="user_1")
        
        assert len(pack.persona) > 0
        assert len(pack.recent_events) > 0
        assert pack.persona[0].key == "assistant_role"
    
    def test_search_items(self, memory_service):
        """测试搜索记忆项"""
        item1 = MemoryItem(
            scope="global",
            kind="knowledge",
            key="python_facts",
            content="Python is a powerful programming language",
            source="system",
        )
        
        item2 = MemoryItem(
            scope="global",
            kind="knowledge",
            key="web_facts",
            content="Web development requires HTML, CSS, JavaScript",
            source="system",
        )
        
        memory_service.upsert_item(item1)
        memory_service.upsert_item(item2)
        
        # 搜索应该返回相关项
        results = memory_service.search_items("programming language", topk=5)
        assert len(results) >= 1


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
