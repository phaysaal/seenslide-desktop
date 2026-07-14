"""Foreground-window state detection — is the on-screen app a real presentation?

Answers one question per frame: *is the app currently on screen a real
presentation (fullscreen OR maximized), or an ordinary windowed app / the
desktop?* This is what lets slide filtering keep only genuine slides even when
the presenter uses a **maximized** (not strictly fullscreen) slide viewer — a
case the image-only taskbar heuristic can't handle, since a maximized window
shows the taskbar exactly like the desktop does.

Backends:
  * X11 (Linux): EWMH `_NET_WM_STATE` via `xprop`.
  * Windows: Win32 `GetForegroundWindow` + `GetWindowPlacement` (maximized) and
    window-rect-vs-monitor (fullscreen), via ctypes (no extra dependency).

Everywhere else (Wayland, macOS) it reports `available=False`, so callers fail
*open* — they never drop a frame just because state couldn't be read. On those
platforms filtering falls back to the reference-desktop image heuristic.
"""
import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Our own window must never be gated on — when SeenSlide itself is focused we
# can't conclude anything about what the presenter is showing.
_OWN_MARKERS = ("seenslide",)

_IS_WINDOWS = sys.platform == "win32"
_XPROP = shutil.which("xprop") if sys.platform.startswith("linux") else None

_UNAVAILABLE = {
    "available": False, "presentation": False, "fullscreen": False,
    "maximized": False, "own": False, "wm_class": "",
}


def _is_own(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in _OWN_MARKERS)


# --------------------------------------------------------------------------- #
# X11 backend (xprop / EWMH)
# --------------------------------------------------------------------------- #

def _x11_available() -> bool:
    return bool(_XPROP) and os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland"


def _xprop(*args: str) -> str:
    if not _XPROP:
        return ""
    try:
        out = subprocess.run(
            [_XPROP, *args], capture_output=True, text=True, timeout=1.0,
        )
        return out.stdout or ""
    except Exception as e:
        logger.debug(f"xprop {args} failed: {e}")
        return ""


def _x11_active_window_id() -> Optional[str]:
    out = _xprop("-root", "_NET_ACTIVE_WINDOW")
    m = re.search(r"(0x[0-9a-fA-F]+)", out)
    if not m or int(m.group(1), 16) == 0:
        return None
    return m.group(1)


def _x11_state() -> dict:
    result = dict(_UNAVAILABLE)
    wid = _x11_active_window_id()
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
        fullscreen=fullscreen, maximized=maximized, wm_class=wm_class,
        own=_is_own(wm_class), presentation=(fullscreen or maximized),
    )
    return result


# --------------------------------------------------------------------------- #
# Windows backend (Win32 via ctypes)
# --------------------------------------------------------------------------- #

def _win_state() -> dict:
    result = dict(_UNAVAILABLE)
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Correct handle widths on 64-bit — without these ctypes assumes c_int
        # and truncates HWND/HMONITOR pointers, yielding bogus handles.
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]

        class WINDOWPLACEMENT(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.UINT), ("flags", wintypes.UINT),
                ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT),
                ("rcNormalPosition", wintypes.RECT),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
            ]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            # Nothing focused (desktop) — available, but not a presentation.
            result["available"] = True
            return result
        result["available"] = True

        # Title + class, for the own-window guard and for logging.
        n = user32.GetWindowTextLengthW(hwnd)
        tbuf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, tbuf, n + 1)
        title = tbuf.value or ""
        cbuf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cbuf, 256)
        cls = cbuf.value or ""
        wm_class = f'"{cls}", "{title}"'

        # Maximized: WINDOWPLACEMENT.showCmd == SW_SHOWMAXIMIZED (3).
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(WINDOWPLACEMENT)
        maximized = bool(
            user32.GetWindowPlacement(hwnd, ctypes.byref(wp))
            and wp.showCmd == 3
        )

        # Fullscreen: a borderless window whose rect covers the whole monitor
        # (a maximized window only covers the work area, leaving the taskbar).
        fullscreen = False
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            hmon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                m = mi.rcMonitor
                fullscreen = (
                    rect.left <= m.left and rect.top <= m.top
                    and rect.right >= m.right and rect.bottom >= m.bottom
                )

        result.update(
            fullscreen=fullscreen, maximized=maximized, wm_class=wm_class,
            own=_is_own(f"{title} {cls}"),
            presentation=(fullscreen or maximized),
        )
        return result
    except Exception as e:
        logger.debug(f"win window-state failed: {e}")
        return dict(_UNAVAILABLE)


# --------------------------------------------------------------------------- #
# Public API (platform dispatch)
# --------------------------------------------------------------------------- #

def is_available() -> bool:
    """True when foreground-window state can be read (X11 or Windows)."""
    return _IS_WINDOWS or _x11_available()


def foreground_state() -> dict:
    """Describe the current foreground window.

    Returns a dict with:
      available   – could we read window state at all?
      presentation– True if fullscreen OR maximized (treat frame as a slide)
      fullscreen  – window is (borderless) fullscreen
      maximized   – window is maximized
      own         – the focused window is SeenSlide's own window
      wm_class    – which app is focused (raw class/title string)
    """
    if _IS_WINDOWS:
        return _win_state()
    if _x11_available():
        return _x11_state()
    return dict(_UNAVAILABLE)
