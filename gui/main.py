#!/usr/bin/env python3
"""SeenSlide GUI Application - Main Entry Point."""

import sys
import logging
from typing import Optional

from PyQt5.QtWidgets import QApplication, QMessageBox

from gui.windows.main_dashboard import MainDashboard

from seenslide import __version__
from core.updater import UpdateChecker, UpdateDownloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class SeenSlideApp:
    """Main application controller."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("SeenSlide")
        self.app.setOrganizationName("SeenSlide")

        self.main_window: Optional[MainDashboard] = None
        self._update_checker: Optional[UpdateChecker] = None
        self._update_downloader: Optional[UpdateDownloader] = None
        self._pending_update: Optional[dict] = None

    def run(self) -> int:
        self.main_window = MainDashboard()
        self.main_window.show()

        self._start_update_check()

        return self.app.exec_()

    # ------------------------------------------------------------------
    # Auto-update
    # ------------------------------------------------------------------

    def _start_update_check(self):
        """Launch background thread to check for updates and messages."""
        self._update_checker = UpdateChecker(current_version=__version__)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.message_available.connect(self._on_message_available)
        self._update_checker.start()

    def _on_update_available(self, info: dict):
        """A newer version was found on the server."""
        self._pending_update = info
        version = info.get("version", "?")
        notes = info.get("release_notes", "") or ""
        msg = f"SeenSlide {version} is available.\n\n{notes}\n\nDownload now?"
        reply = QMessageBox.question(
            self.main_window,
            "Update Available",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._on_download_requested(info)

    def _on_message_available(self, msg: dict):
        """A broadcast message arrived."""
        title = msg.get("title", "Notice")
        body = msg.get("body", "")
        QMessageBox.information(self.main_window, title, body)
        msg_id = msg.get("id")
        if msg_id:
            UpdateChecker.dismiss_message(msg_id)

    def _on_download_requested(self, info: dict):
        url = info.get("download_url", "")
        if not url:
            logger.warning("No download URL in update info")
            return

        self._update_downloader = UpdateDownloader(
            url=url,
            expected_sha256=info.get("sha256", ""),
        )
        self._update_downloader.download_complete.connect(self._on_download_complete)
        self._update_downloader.download_failed.connect(self._on_download_failed)
        self._update_downloader.start()

    def _on_download_complete(self, file_path: str):
        reply = QMessageBox.question(
            self.main_window,
            "Update Downloaded",
            "The update has been downloaded. Install and restart now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            from gui.widgets.update_banner import UpdateBanner
            UpdateBanner.launch_installer(file_path)

    def _on_download_failed(self, reason: str):
        QMessageBox.warning(
            self.main_window,
            "Update Failed",
            f"Could not download the update:\n\n{reason}",
        )


def main():
    """Main entry point."""
    try:
        app = SeenSlideApp()
        exit_code = app.run()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
