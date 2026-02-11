from __future__ import annotations

from pathlib import Path
import pytest

from src.gate.config import GateConfig
from src.gate.types import Scene


def test_load_gate_yaml():
    cfg = GateConfig.from_yaml(Path("config/gate.yaml"))
    assert cfg.version == 1
    assert cfg.scene_policy(Scene.DIALOGUE).deliver_threshold > 0


def test_missing_scene_policy_fallback(tmp_path: Path):
    content = """
version: 1
scene_policies:
  dialogue:
    deliver_threshold: 0.9
"""
    path = tmp_path / "gate.yaml"
    path.write_text(content, encoding="utf-8")

    cfg = GateConfig.from_yaml(path)
    # group 缺省但不崩
    policy = cfg.scene_policy(Scene.GROUP)
    assert policy.default_action is not None


def test_version_mismatch_raises(tmp_path: Path):
    content = """
version: 2
scene_policies: {}
"""
    path = tmp_path / "gate.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        GateConfig.from_yaml(path)
