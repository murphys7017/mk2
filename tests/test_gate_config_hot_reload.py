from __future__ import annotations

import os
from pathlib import Path

from src.config_provider import GateConfigProvider
from src.gate.types import Scene


def test_gate_config_hot_reload(tmp_path: Path):
    path = tmp_path / "gate.yaml"
    path.write_text(
        """
version: 1
scene_policies:
  dialogue:
    deliver_threshold: 0.8
""",
        encoding="utf-8",
    )

    provider = GateConfigProvider(path)
    cfg1 = provider.snapshot()
    assert cfg1.scene_policy(Scene.DIALOGUE).deliver_threshold == 0.8
    old_mtime = path.stat().st_mtime

    # 修改配置
    path.write_text(
        """
version: 1
scene_policies:
  dialogue:
    deliver_threshold: 0.95
""",
        encoding="utf-8",
    )

    # 强制保持相同 mtime，模拟 Windows 上 mtime 精度问题
    os.utime(path, (old_mtime, old_mtime))

    changed = provider.reload_if_changed()
    cfg2 = provider.snapshot()

    assert changed is True
    assert cfg2 is not cfg1
    assert cfg2.scene_policy(Scene.DIALOGUE).deliver_threshold == 0.95
