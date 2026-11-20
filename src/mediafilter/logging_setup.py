"""Rotating file log so a user report can be diagnosed after the fact.

The API key and the frames never reach this file: callers log short, already
sanitized messages (``safe_error`` masks keys before they are logged).
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import platformdirs

_LOG_NAME = "mediafilter.log"


def log_path() -> Path:
    return Path(platformdirs.user_config_dir("media-filter-v2", appauthor=False)) / _LOG_NAME


def configure_logging() -> Path:
    """Attach a 1 MB x 3 rotating handler to the root logger; return the path."""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    def log_uncaught(exc_type, exc, tb) -> None:
        logging.getLogger("mediafilter").error(
            "uncaught exception", exc_info=(exc_type, exc, tb)
        )
        sys.__excepthook__(exc_type, exc, tb)

    def log_thread_uncaught(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is None:
            return
        logging.getLogger("mediafilter").error(
            "uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_uncaught
    return path