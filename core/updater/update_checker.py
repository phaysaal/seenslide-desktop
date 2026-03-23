"""Background update checker - checks for new versions and messages on startup."""

import logging
import platform
import yaml
import requests
from pathlib import Path
from typing import Dict, Any, Tuple

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

DISMISSED_FILE = Path.home() / ".config" / "seenslide" / ".dismissed_messages"


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse version string like '1.2.3' or 'v1.2.3' into comparable tuple."""
    v = version_str.lstrip("v").strip()
    return tuple(int(p) for p in v.split(".")[:3])


def is_newer(latest: str, current: str) -> bool:
    """Return True if latest version is newer than current."""
    try:
        return parse_version(latest) > parse_version(current)
    except (ValueError, IndexError):
        return False


def _get_cloud_api_url() -> str:
    """Read cloud API URL from config/config.yaml."""
    try:
        config_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
        if config_path.exists():
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)
            cloud = cfg.get("cloud", {})
            if cloud.get("enabled") and cloud.get("api_url"):
                return cloud["api_url"].rstrip("/")
    except Exception:
        pass
    return ""


def _get_platform() -> str:
    """Get platform identifier: linux, darwin, or windows."""
    return platform.system().lower()


class UpdateChecker(QThread):
    """Background thread that checks for updates and broadcast messages.

    Signals:
        update_available(dict): Emitted when a newer version exists.
        message_available(dict): Emitted per undismissed message from the server.
        check_complete(): Emitted when the check finishes (success or failure).
        check_failed(str): Emitted with an error description on failure.
    """

    update_available = pyqtSignal(dict)
    message_available = pyqtSignal(dict)
    check_complete = pyqtSignal()
    check_failed = pyqtSignal(str)

    def __init__(self, current_version: str, check_url: str = "", parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self._platform = _get_platform()

        # Resolve check URL: explicit > config > skip
        if check_url:
            self.check_url = check_url.rstrip("/")
        else:
            base = _get_cloud_api_url()
            self.check_url = f"{base}/api/updates/check" if base else ""

    # ------------------------------------------------------------------

    def run(self):
        if not self.check_url:
            logger.debug("Update check skipped — no API URL configured")
            self.check_complete.emit()
            return

        try:
            logger.info(f"Checking for updates at {self.check_url} (v{self.current_version})")

            resp = requests.get(
                self.check_url,
                params={
                    "version": self.current_version,
                    "platform": self._platform,
                },
                timeout=8,
                headers={"User-Agent": f"SeenSlide/{self.current_version}"},
            )

            if resp.status_code != 200:
                self.check_failed.emit(f"HTTP {resp.status_code}")
                self.check_complete.emit()
                return

            self._process_response(resp.json())

        except requests.exceptions.ConnectionError:
            logger.debug("Update check: no connectivity")
            self.check_failed.emit("No internet connection")
        except requests.exceptions.Timeout:
            logger.debug("Update check: timed out")
            self.check_failed.emit("Request timed out")
        except Exception as e:
            logger.warning(f"Update check failed: {e}")
            self.check_failed.emit(str(e))
        finally:
            self.check_complete.emit()

    # ------------------------------------------------------------------

    def _process_response(self, data: Dict[str, Any]):
        latest = data.get("latest_version", "")
        if latest and is_newer(latest, self.current_version):
            downloads = data.get("downloads", {})
            checksums = data.get("sha256", {})
            sizes = data.get("file_size", {})

            info = {
                "version": latest,
                "release_notes": data.get("release_notes", ""),
                "release_date": data.get("release_date", ""),
                "download_url": downloads.get(self._platform, ""),
                "sha256": checksums.get(self._platform, ""),
                "file_size": sizes.get(self._platform, 0),
                "is_critical": data.get("is_critical", False),
            }
            logger.info(f"Update available: v{latest}")
            self.update_available.emit(info)
        else:
            logger.info(f"Up to date (v{self.current_version})")

        # Broadcast messages
        dismissed = _load_dismissed()
        for msg in data.get("messages", []):
            mid = msg.get("id", "")
            if mid and mid not in dismissed:
                self.message_available.emit(msg)

    # ------------------------------------------------------------------
    # Dismissed-message persistence
    # ------------------------------------------------------------------

    @staticmethod
    def dismiss_message(msg_id: str):
        """Record a message ID so it won't be shown again."""
        try:
            dismissed = _load_dismissed()
            dismissed.add(msg_id)
            DISMISSED_FILE.parent.mkdir(parents=True, exist_ok=True)
            DISMISSED_FILE.write_text("\n".join(sorted(dismissed - {""})))
        except Exception as e:
            logger.warning(f"Could not persist dismissed message: {e}")


def _load_dismissed() -> set:
    try:
        if DISMISSED_FILE.exists():
            return set(DISMISSED_FILE.read_text().strip().splitlines())
    except Exception:
        pass
    return set()
