from __future__ import annotations

from pathlib import Path

from src.core import Core


class DummyOrchestrator:
    async def handle(self, req):
        raise RuntimeError("not used in this test")


def _write_memory_config(path: Path, vault_root: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "database:",
                "  dsn: \"sqlite:///:memory:\"",
                "  pool_size: 5",
                "  max_overflow: 10",
                "vault:",
                f"  root_path: \"{vault_root.as_posix()}\"",
                "failure_queue:",
                "  max_in_memory: 100",
                "  spill_batch_size: 10",
                "  max_dump_file_size_mb: 1",
                "  max_dump_backups: 1",
                "  max_retries: 3",
            ]
        ),
        encoding="utf-8",
    )


def test_core_memory_autoinit_success(tmp_path):
    cfg_path = tmp_path / "memory.yaml"
    vault_root = tmp_path / "vault"
    _write_memory_config(cfg_path, vault_root)

    core = Core(
        enable_memory=True,
        memory_config_path=str(cfg_path),
        enable_session_gc=False,
        agent_queen=DummyOrchestrator(),
    )
    try:
        assert core.memory_service is not None
    finally:
        if core.memory_service is not None:
            core.memory_service.close()


def test_core_memory_autoinit_fail_open(tmp_path):
    cfg_path = tmp_path / "invalid_memory.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "database:",
                "  dsn: \"invalid+driver://user:pass@localhost:1234/db\"",
                "vault:",
                f"  root_path: \"{(tmp_path / 'vault_invalid').as_posix()}\"",
            ]
        ),
        encoding="utf-8",
    )
    core = Core(
        enable_memory=True,
        memory_config_path=str(cfg_path),
        enable_session_gc=False,
        agent_queen=DummyOrchestrator(),
    )
    try:
        assert core.memory_service is None
    finally:
        if core.memory_service is not None:
            core.memory_service.close()
