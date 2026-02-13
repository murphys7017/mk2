from __future__ import annotations

import logging
import sys
from typing import Callable, Optional

from loguru import logger


_configured = False


class _InterceptHandler(logging.Handler):
    """Forward standard logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(
    *,
    level: str = "INFO",
    force: bool = False,
    trace_key: Optional[str] = None,
    trace_only: bool = False,
    fmt: Optional[str] = None,
) -> None:
    """
    Configure a single global loguru sink for the whole project.

    Parameters:
    - level: minimum level for trace logs and normal logs.
    - force: reconfigure even if already configured.
    - trace_key: loguru `extra` key used to mark trace logs.
    - trace_only: if True, keep only trace logs + warning/error.
    - fmt: optional custom format.
    """
    global _configured

    if _configured and not force:
        return

    logger.remove()

    if trace_only and trace_key:
        def _filter(record) -> bool:
            if record["extra"].get(trace_key):
                return True
            return record["level"].name in ("WARNING", "ERROR", "CRITICAL")
    else:
        def _filter(record) -> bool:
            return record["level"].no >= logger.level(level.upper()).no

    logger.add(
        sys.stderr,
        level=level.upper(),
        colorize=True,
        filter=_filter,
        format=(
            fmt
            or "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>"
        ),
    )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    _configured = True

