"""Persistent user preferences for the desktop app.

Stored as JSON at ~/.config/seenslide/.app_settings.json. Use this for
non-secret user choices that should survive launches — e.g. which monitor
to capture, the last-used dedup sensitivity, etc. (For auth credentials,
use core.session.credential_manager. For identity-server state, use
core.identity.)

Read/write is best-effort: a corrupted or missing file falls back to
defaults and the next save heals it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path.home() / ".config" / "seenslide" / ".app_settings.json"

_DEFAULTS: Dict[str, Any] = {
    "monitor_id": 1,
}


def _load() -> Dict[str, Any]:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.debug(f"app_settings unreadable, using defaults: {e}")
    return {}


def _save(data: Dict[str, Any]) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        SETTINGS_FILE.chmod(0o600)
    except Exception as e:
        logger.warning(f"could not save app_settings: {e}")


def get(key: str, default: Any = None) -> Any:
    """Read a setting. Falls back to module defaults, then `default`."""
    data = _load()
    if key in data:
        return data[key]
    if key in _DEFAULTS:
        return _DEFAULTS[key]
    return default


def set_value(key: str, value: Any) -> None:
    """Write a setting and flush to disk."""
    data = _load()
    data[key] = value
    _save(data)
