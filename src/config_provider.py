from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple

from .gate.config import GateConfig

logger = logging.getLogger(__name__)


class GateConfigProvider:
    """Core 侧 GateConfig 快照提供者"""

    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path)
        self._ref: GateConfig = GateConfig.default()
        self._last_stamp: Optional[Tuple[int, int]] = None
        self._last_hash: Optional[str] = None

        self.force_reload()

    def snapshot(self) -> GateConfig:
        return self._ref

    def reload_if_changed(self) -> bool:
        stamp = self._safe_file_stamp()
        if stamp is None:
            return False

        if self._last_stamp is not None and stamp == self._last_stamp:
            # mtime 在部分平台上精度不稳定，补充 hash 判定内容变化
            current_hash = self._safe_file_hash()
            if current_hash is None or current_hash == self._last_hash:
                return False

        return self.force_reload()

    def force_reload(self) -> bool:
        try:
            cfg = GateConfig.from_yaml(self._path)
            self._ref = cfg
            self._last_stamp = self._safe_file_stamp()
            self._last_hash = self._safe_file_hash()
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

    def _safe_file_stamp(self) -> Optional[Tuple[int, int]]:
        try:
            stat = self._path.stat()
            return stat.st_mtime_ns, stat.st_size
        except Exception as e:
            logger.warning(f"Gate config stat failed: {e}")
            return None

    def _safe_file_hash(self) -> Optional[str]:
        try:
            data = self._path.read_bytes()
            return hashlib.sha256(data).hexdigest()
        except Exception as e:
            logger.warning(f"Gate config hash failed: {e}")
            return None
