from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .gate.config import GateConfig

logger = logging.getLogger(__name__)


class GateConfigProvider:
    """Core 侧 GateConfig 快照提供者"""

    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path)
        self._ref: GateConfig = GateConfig.default()
        self._last_mtime: Optional[float] = None

        self.force_reload()

    def snapshot(self) -> GateConfig:
        return self._ref

    def reload_if_changed(self) -> bool:
        try:
            mtime = self._path.stat().st_mtime
        except Exception as e:
            logger.warning(f"Gate config stat failed: {e}")
            return False

        if self._last_mtime is not None and mtime <= self._last_mtime:
            return False

        return self.force_reload()

    def force_reload(self) -> bool:
        try:
            cfg = GateConfig.from_yaml(self._path)
            self._ref = cfg
            try:
                self._last_mtime = self._path.stat().st_mtime
            except Exception:
                self._last_mtime = None
            logger.info("Gate config reloaded")
            return True
        except Exception as e:
            logger.warning(f"Gate config reload failed: {e}")
            return False

    def update_overrides(self, **kwargs) -> bool:
        """Update overrides by replacing snapshot reference. Returns True if changed."""
        try:
            current = self._ref
            updated = current.with_overrides(**kwargs)
            if updated is current:
                return False
            self._ref = updated
            return True
        except Exception as e:
            logger.warning(f"Gate overrides update failed: {e}")
            return False
