"""Deterministic side of the harness: real input events + app lifecycle.

xdotool synthesizes OS-level mouse/keyboard events on X11 — indistinguishable
from a human, so the app's input-monitor capture trigger fires naturally.

The app runs under a SANDBOXED HOME: the user's real settings, collections,
credentials and slide database are never touched, and the sandbox config
points the cloud at a dead localhost port so nothing leaves the machine.
"""
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import mss

logger = logging.getLogger(__name__)

PROJECT = Path(__file__).resolve().parents[1]
APP_WINDOW_TITLE = "SeenSlide Pro"


# ---------------------------------------------------------------------------
# Input events
# ---------------------------------------------------------------------------

def _xdo(*args):
    subprocess.run(["xdotool", *args], check=True, capture_output=True, text=True)


def click(x: int, y: int):
    _xdo("mousemove", str(x), str(y), "click", "1")
    time.sleep(0.4)


def type_text(text: str):
    _xdo("type", "--delay", "40", text)
    time.sleep(0.2)


def press_key(key: str):
    _xdo("key", key)
    time.sleep(0.2)


# Global offset of the last-captured monitor: screenshot pixel coords ->
# X11 desktop coords for xdotool. On a single monitor this is (0,0); with
# multiple monitors it's what kept clicks from landing on the wrong screen.
_monitor_offset = (0, 0)


def screenshot(path: str, monitor: int = 1):
    """Full-monitor PNG. Returns (width, height)."""
    global _monitor_offset
    with mss.mss() as sct:
        mon = sct.monitors[monitor]
        _monitor_offset = (mon.get("left", 0), mon.get("top", 0))
        img = sct.grab(mon)
        mss.tools.to_png(img.rgb, img.size, output=path)
        return img.size


def click_shot_coords(x: int, y: int):
    """Click at screenshot-relative coordinates (offset-corrected)."""
    click(x + _monitor_offset[0], y + _monitor_offset[1])


# ---------------------------------------------------------------------------
# App lifecycle (sandboxed)
# ---------------------------------------------------------------------------

class App:
    def __init__(self):
        self.proc = None
        self.sandbox = None

    def make_sandbox(self) -> Path:
        """Fresh HOME with consent pre-answered and the cloud pointed at a
        dead local port (fast, silent failures — fully offline behavior)."""
        self.sandbox = Path(tempfile.mkdtemp(prefix="seenslide-gui-test-"))
        cfg_dir = self.sandbox / ".config" / "seenslide"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / ".app_settings.json").write_text(
            '{"cloud_consent": false, "theme": "dark", "slide_gate_enabled": false}'
        )
        (cfg_dir / "config.yaml").write_text(
            "cloud:\n"
            "  enabled: false\n"
            "  api_url: http://127.0.0.1:9\n"
        )
        return self.sandbox

    def launch(self, wait: float = 8.0):
        self.make_sandbox()
        env = dict(os.environ)
        env["HOME"] = str(self.sandbox)
        env["XDG_DATA_HOME"] = str(self.sandbox / ".local" / "share")
        env["XDG_CONFIG_HOME"] = str(self.sandbox / ".config")
        # Stay above other windows (GNOME ignores external raise requests,
        # so the app raises itself via this in-app test hook).
        env["SEENSLIDE_TEST_ON_TOP"] = "1"
        # Never touch the real system keyring: the sandbox app querying the
        # Secret Service popped the user's password-manager unlock dialog on
        # top of everything mid-run. The null backend makes keyring a no-op;
        # the app degrades to anonymous/local, which is what we want anyway.
        env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
        logger.info(f"launching app (sandbox HOME={self.sandbox})")
        self.proc = subprocess.Popen(
            [str(PROJECT / "venv" / "bin" / "python3"), "gui/main.py"],
            cwd=str(PROJECT), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(wait)
        if self.proc.poll() is not None:
            raise RuntimeError(f"app exited immediately (code {self.proc.returncode})")
        self.position_window()

    def position_window(self, x: int = 60, y: int = 40):
        """Fixed position → stable screenshots → the coordinate cache stays
        valid across runs."""
        try:
            out = subprocess.run(
                ["xdotool", "search", "--name", APP_WINDOW_TITLE],
                capture_output=True, text=True, timeout=10)
            wid = (out.stdout.split() or [""])[0]
            if wid:
                _xdo("windowmove", wid, str(x), str(y))
                _xdo("windowactivate", wid)
                _xdo("windowraise", wid)
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"could not position window: {e}")

    def ensure_front(self):
        """Raise + focus the app before a screenshot, so windows the user
        left (or opened) on top can't occlude the run. During a harness run
        the machine belongs to the harness."""
        if self.proc and self.proc.poll() is None:
            self.position_window()

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def cleanup(self):
        self.kill()
        if self.sandbox and self.sandbox.exists():
            shutil.rmtree(self.sandbox, ignore_errors=True)

    @property
    def log_file(self) -> Path:
        return self.sandbox / ".local" / "share" / "seenslide" / "logs" / "seenslide.log"
