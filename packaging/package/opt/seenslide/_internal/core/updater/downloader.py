"""Background file downloader with progress reporting and SHA-256 verification."""

import hashlib
import logging
import os
import platform
from pathlib import Path

import requests
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "seenslide" / "updates"


class UpdateDownloader(QThread):
    """Downloads an update artifact in the background.

    Signals:
        progress(int, int): (bytes_downloaded, total_bytes)
        download_complete(str): Absolute path to the downloaded file.
        download_failed(str): Human-readable error message.
    """

    progress = pyqtSignal(int, int)
    download_complete = pyqtSignal(str)
    download_failed = pyqtSignal(str)

    def __init__(self, url: str, expected_sha256: str = "", parent=None):
        super().__init__(parent)
        self.url = url
        self.expected_sha256 = expected_sha256.lower().strip()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            filename = self.url.rsplit("/", 1)[-1] or "seenslide-update"
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            dest = CACHE_DIR / filename

            logger.info(f"Downloading {self.url} -> {dest}")

            resp = requests.get(
                self.url,
                stream=True,
                timeout=30,
                headers={"User-Agent": "SeenSlide/updater"},
            )
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            sha = hashlib.sha256()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65_536):
                    if self._cancelled:
                        dest.unlink(missing_ok=True)
                        self.download_failed.emit("Cancelled")
                        return
                    f.write(chunk)
                    sha.update(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, total)

            # Verify checksum
            if self.expected_sha256:
                actual = sha.hexdigest()
                if actual != self.expected_sha256:
                    dest.unlink(missing_ok=True)
                    self.download_failed.emit(
                        f"Checksum mismatch (expected {self.expected_sha256[:12]}…)"
                    )
                    return
                logger.info("SHA-256 verified")

            # Make executable on Unix
            if platform.system() != "Windows":
                os.chmod(dest, 0o755)

            logger.info(f"Download complete: {dest}")
            self.download_complete.emit(str(dest))

        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed: {e}")
            self.download_failed.emit(str(e))
        except Exception as e:
            logger.error(f"Download error: {e}")
            self.download_failed.emit(str(e))
