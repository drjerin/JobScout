"""Project logging with size-based rotation.

A single call to :func:`setup` at process start wires up both the console
handler (so `python run.py` still shows progress live) and a rotating file
handler under ``state/scout.log``.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_LOG_DIR = _ROOT / "state"
_LOG_FILE = _LOG_DIR / "scout.log"

_configured = False


def setup(level: int = logging.INFO) -> logging.Logger:
    """Configure the root logger idempotently and return the project logger."""
    global _configured
    logger = logging.getLogger("scout")
    if _configured:
        return logger

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_h = RotatingFileHandler(
        _LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_h.setFormatter(fmt)

    stream_h = logging.StreamHandler(stream=sys.stdout)
    stream_h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace any pre-existing handlers so re-imports don't double-log.
    root.handlers = [file_h, stream_h]

    # Quiet chatty libraries.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    _configured = True
    return logger


def get(name: str = "scout") -> logging.Logger:
    """Return a namespaced logger (assumes :func:`setup` has been called)."""
    return logging.getLogger(name)
