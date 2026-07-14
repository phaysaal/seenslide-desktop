"""Foreground-window state detection on X11 (EWMH, via `xprop`).

Answers one question per frame: *is the app currently on screen a real
presentation (fullscreen OR maximized), or an ordinary windowed app / the
desktop?* This is what lets us keep only genuine slides in the deck even when
the presenter uses a **maximized** (not strictly fullscreen) slide viewer — a
case the image-only taskbar heuristic can't handle, since a maximized window
still shows the taskbar exactly like the desktop does.

How: read `_NET_ACTIVE_WINDOW` off the root window, then that window's
`_NET_WM_STATE` (for `_FULLSCREEN` / `_MAXIMIZED_HORZ`+`_MAXIMIZED_VERT`) and
`WM_CLASS`. These are standard EWMH properties every X11 window manager sets.

X11 only. On Wayland (no window introspection) or on any error it reports
`available=False`, so callers fail *open* — they never drop a frame just
because the state couldn't be read.
"""
import logging
import os
import re
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Our own window must never be gated on — when SeenSlide itself is focused we
# can't conclude anything about what the presenter is showing.
_OWN_WM_CLASSES = ("seenslide",)

_XPROP = shutil.which("xprop")


def _xprop(*args: str) -> str:
    if not _XPROP:
        return ""
    try:
        out = subprocess.run(
            [_XPROP, *args],
            capture_output=True, text=True, timeout=1.0,
        )
        return out.stdout or ""
    except Exception as e:  # subprocess failure, timeout, etc.
        logger.debug(f"xprop {args} failed: {e}")
        return ""


def _active_window_id() -> Optional[str]:
    out = _xprop("-root", "_NET_ACTIVE_WINDOW")
    m = re.search(r"(0x[0-9a-fA-F]+)", out)
    if not m or int(m.group(1), 16) == 0:
        return None
    return m.group(1)


def is_available() -> bool:
    """True only on an X11 session with xprop present."""
    return (
        bool(_XPROP)
        and os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland"
    )


def foreground_state() -> dict:
    """Describe the current foreground window.

    Returns a dict with:
      available   – could we read window state at all (X11 + xprop)?
      presentation– True if fullscreen OR maximized (treat frame as a slide)
      fullscreen  – _NET_WM_STATE_FULLSCREEN present
      maximized   – both maximized-horz and maximized-vert present
      own         – the focused window is SeenSlide's own window
      wm_class    – raw WM_CLASS string (which app is focused)
    """
    result = {
        "available": False, "presentation": False, "fullscreen": False,
        "maximized": False, "own": False, "wm_class": "",
    }
    if not is_available():
        return result

    wid = _active_window_id()
    if not wid:
        # No active window usually means the desktop is focused — not a slide.
        result["available"] = True
        return result

    props = _xprop("-id", wid, "_NET_WM_STATE", "WM_CLASS")
    if not props:
        return result

    result["available"] = True
    fullscreen = "_NET_WM_STATE_FULLSCREEN" in props
    maximized = (
        "_NET_WM_STATE_MAXIMIZED_HORZ" in props
        and "_NET_WM_STATE_MAXIMIZED_VERT" in props
    )
    wm_class = ""
    m = re.search(r"WM_CLASS\(STRING\) = (.+)", props)
    if m:
        wm_class = m.group(1).strip()

    result.update(
        fullscreen=fullscreen,
        maximized=maximized,
        wm_class=wm_class,
        own=any(o in wm_class.lower() for o in _OWN_WM_CLASSES),
        presentation=(fullscreen or maximized),
    )
    return result
