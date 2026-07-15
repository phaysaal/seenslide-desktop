"""Deterministic side of the harness: real input events + app lifecycle.

xdotool synthesizes OS-level mouse/keyboard events on X11 — indistinguishable
from a human, so the app's input-monitor capture trigger fires naturally.

The app runs under a SANDBOXED HOME: the user's real settings, collections,
credentials and slide database are never touched, and the sandbox config
points the cloud at a dead localhost port so nothing leaves the machine.
"""
import json
import logging
import os
import re
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
# multiple monitors it's what keeps clicks from landing on the wrong screen.
_monitor_offset = (0, 0)
_primary_idx = None


def primary_monitor() -> int:
    """mss index of the PRIMARY monitor (via xrandr), cached.

    With multiple monitors, mss's ordering is arbitrary — the harness must
    capture, click, and place the app window on the same physical screen,
    and that screen should be the user's primary.
    """
    global _primary_idx
    if _primary_idx is not None:
        return _primary_idx
    idx = 1  # sensible fallback
    try:
        out = subprocess.run(["xrandr", "--query"], capture_output=True,
                             text=True, timeout=5).stdout
        import re
        m = re.search(r" connected primary (\d+)x(\d+)\+(\d+)\+(\d+)", out)
        if m:
            w, h, x, y = map(int, m.groups())
            with mss.mss() as sct:
                for i, mon in enumerate(sct.monitors[1:], start=1):
                    if (mon["left"], mon["top"], mon["width"], mon["height"]) == (x, y, w, h):
                        idx = i
                        break
    except Exception as e:
        logger.warning(f"primary-monitor detection failed ({e}); using monitor 1")
    _primary_idx = idx
    logger.info(f"primary monitor -> mss index {idx}")
    return idx


def screenshot(path: str, monitor: int = None):
    """Primary-monitor PNG (or an explicit mss index). Returns (width, height)."""
    global _monitor_offset
    if monitor is None:
        monitor = primary_monitor()
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

    def make_sandbox(self, cloud: bool = False) -> Path:
        """Fresh HOME with consent pre-answered.

        cloud=False (default): fully offline — cloud disabled and pointed at
        a dead local port.

        cloud=True: real cloud E2E under a THROWAWAY ANONYMOUS identity. The
        app's device-bootstrap creates an anonymous account with no email
        needed. Crucially the sandbox pre-seeds a RANDOM device id — without
        it, the app would derive the id from /etc/machine-id and the
        bootstrap would resurrect the user's real anonymous account,
        polluting their collections. Everything the run creates belongs to a
        one-off account no human can log into.

        The sandbox config is the PROJECT config with overrides — a minimal
        config here made the orchestrator fall back to hash dedup and,
        worse, store slides in the shared /tmp/seenslide instead of the
        sandbox (the sqlite provider's own default)."""
        import uuid
        import yaml
        self.sandbox = Path(tempfile.mkdtemp(prefix="seenslide-gui-test-"))
        cfg_dir = self.sandbox / ".config" / "seenslide"
        cfg_dir.mkdir(parents=True)
        consent = "true" if cloud else "false"
        (cfg_dir / ".app_settings.json").write_text(
            f'{{"cloud_consent": {consent}, "theme": "dark", "slide_gate_enabled": false}}'
        )
        # Suppress the anonymous-account sign-in nudges: a fresh identity
        # always triggers tier A on the first slide, and the dialog popped up
        # mid-run over the live view. Pre-seed "already nudged recently".
        import time as _time
        now = _time.time()
        (cfg_dir / ".nudge_state.json").write_text(json.dumps({
            "total_slides": 1,
            "slides_since_last_dismiss": 0,
            "tier_a_shown_at": now,
            "tier_b_last_shown_at": now,
            "tier_c_shown": False,
        }))
        cfg = yaml.safe_load((PROJECT / "config" / "config.yaml").read_text())
        cfg.setdefault("cloud", {})
        if cloud:
            cfg["cloud"]["enabled"] = True
            cfg["cloud"]["api_url"] = "https://seenslide.com"
            (cfg_dir / ".device_id").write_text(f"gui-test-{uuid.uuid4()}")
        else:
            cfg["cloud"]["enabled"] = False
            cfg["cloud"]["api_url"] = "http://127.0.0.1:9"
        cfg.setdefault("storage", {})
        cfg["storage"]["base_path"] = str(self.sandbox / "data")
        (cfg_dir / "config.yaml").write_text(yaml.safe_dump(cfg))
        return self.sandbox

    @property
    def db_path(self) -> Path:
        return self.sandbox / "data" / "db" / "seenslide.db"

    def launch(self, wait: float = 8.0, cloud: bool = False):
        self.make_sandbox(cloud=cloud)
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

    def _app_window_ids(self):
        """Our app's window ids — PID-scoped when possible, so another
        SeenSlide instance (or any window with a matching title) can't be
        moved by mistake."""
        if self.proc and self.proc.poll() is None:
            out = subprocess.run(
                ["xdotool", "search", "--pid", str(self.proc.pid)],
                capture_output=True, text=True, timeout=10)
            wids = out.stdout.split()
            if wids:
                return wids
        out = subprocess.run(
            ["xdotool", "search", "--name", APP_WINDOW_TITLE],
            capture_output=True, text=True, timeout=10)
        return out.stdout.split()

    def position_window(self, x: int = 60, y: int = 40):
        """Fixed position ON THE PRIMARY MONITOR, verified.

        GNOME opens new windows on the monitor holding the mouse pointer —
        on a two-monitor setup that put the app on the wrong screen and a
        single unverified move raced the WM's initial placement. Move, then
        read the geometry back; retry until it actually sits inside the
        primary monitor."""
        try:
            idx = primary_monitor()
            with mss.mss() as sct:
                mon = sct.monitors[idx]
            gx, gy = mon["left"] + x, mon["top"] + y
            wids = self._app_window_ids()
            if not wids:
                logger.warning("app window not found for positioning")
                return
            for attempt in range(4):
                for wid in wids:
                    try:
                        _xdo("windowmove", wid, str(gx), str(gy))
                        _xdo("windowactivate", wid)
                        _xdo("windowraise", wid)
                    except Exception:
                        pass
                time.sleep(0.5)
                geo = subprocess.run(
                    ["xdotool", "getwindowgeometry", wids[-1]],
                    capture_output=True, text=True, timeout=5).stdout
                m = re.search(r"Position:\s*(-?\d+),(-?\d+)", geo)
                if m:
                    wx, wy = int(m.group(1)), int(m.group(2))
                    inside = (mon["left"] <= wx < mon["left"] + mon["width"]
                              and mon["top"] <= wy < mon["top"] + mon["height"])
                    if inside:
                        return
                logger.info(f"window not on primary yet (attempt {attempt + 1}) — retrying")
            logger.warning("could not verify window on primary monitor")
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
