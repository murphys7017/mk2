from __future__ import annotations

import os

from src.memory.config import MemoryConfig


def test_memory_config_from_dict_parses_failure_queue_and_embedding_provider_dimension():
    cfg = MemoryConfig.from_dict(
        {
            "database": {
                "dsn": "sqlite:///:memory:",
                "pool_size": 7,
                "unknown_field": "ignored",
            },
            "vector": {
                "enabled": True,
                "type": "memory",
                "embedding": {
                    "type": "deterministic",
                    "deterministic": {"dimension": "256"},
                    "ignored": "x",
                },
            },
            "failure_queue": {
                "max_in_memory": 123,
                "spill_batch_size": 11,
                "max_dump_file_size_mb": 9,
                "max_dump_backups": 2,
                "max_retries": 5,
                "extra": "ignored",
            },
            "unknown_top_level": {"x": 1},
        }
    )

    assert cfg.database.dsn == "sqlite:///:memory:"
    assert cfg.database.pool_size == 7
    assert cfg.vector.enabled is True
    assert cfg.vector.embedding.type == "deterministic"
    assert cfg.vector.embedding.dimension == 256
    assert cfg.failure_queue.max_in_memory == 123
    assert cfg.failure_queue.spill_batch_size == 11
    assert cfg.failure_queue.max_dump_file_size_mb == 9
    assert cfg.failure_queue.max_dump_backups == 2
    assert cfg.failure_queue.max_retries == 5


def test_memory_config_from_yaml_replaces_env_vars(tmp_path, monkeypatch):
    cfg_path = tmp_path / "memory.yaml"
    monkeypatch.setenv("TEST_MEMORY_DSN", "sqlite:///:memory:")
    cfg_path.write_text(
        "\n".join(
            [
                "database:",
                "  dsn: \"<TEST_MEMORY_DSN>\"",
                "failure_queue:",
                "  max_retries: 17",
            ]
        ),
        encoding="utf-8",
    )

    cfg = MemoryConfig.from_yaml(cfg_path)
    assert cfg.database.dsn == "sqlite:///:memory:"
    assert cfg.failure_queue.max_retries == 17
