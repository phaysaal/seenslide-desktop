"""App-wide logging + crash capture.

A packaged GUI app launched from a desktop icon has its stdout discarded, so
console-only logging means a user who hits a crash has nothing to send us.
This module gives every run a rotating log file and hooks uncaught exceptions
— including ones raised inside Qt slots and background threads, which never
reach the try/except around app.exec_() — so they land in that file too.

Usage (once, at the top of each entry point):

    from core.logging_setup import setup_logging
    setup_logging()
"""
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_MAX_BYTES = 2 * 1024 * 1024   # 2 MB per file
_BACKUP_COUNT = 3              # seenslide.log + .1/.2/.3 ≈ 8 MB cap
_configured = False


def get_log_dir() -> Path:
    """Platform-appropriate directory for log files."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SeenSlide" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "SeenSlide"
    # Linux/other: XDG data dir
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "seenslide" / "logs"


def get_log_file() -> Path:
    return get_log_dir() / "seenslide.log"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure console + rotating-file logging and install crash hooks.

    Idempotent: safe to call from multiple entry points; only the first call
    configures handlers.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(console)

    # File handler is best-effort: a read-only or exotic environment must
    # never prevent the app from starting.
    try:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        # utf-8 explicitly — log lines contain emoji, and Windows' default
        # locale encoding would raise UnicodeEncodeError on them.
        file_handler = logging.handlers.RotatingFileHandler(
            get_log_file(), maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(file_handler)
        root.info(f"Logging to {get_log_file()}")
    except Exception as e:
        root.warning(f"File logging unavailable ({e}); console only")

    _install_crash_hooks()


def _install_crash_hooks() -> None:
    """Log uncaught exceptions from the main thread, Qt slots, and threads.

    PyQt5 routes unhandled exceptions in slots through sys.excepthook — with
    the default hook it prints to (discarded) stderr and aborts the process.
    Our hook records the traceback to the log file and lets the app keep
    running for slot errors, which are usually recoverable UI-level bugs.
    KeyboardInterrupt keeps its normal behaviour.
    """
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("crash").critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _hook

    def _thread_hook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logging.getLogger("crash").critical(
            f"Uncaught exception in thread {args.thread.name if args.thread else '?'}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook
