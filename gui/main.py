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
        self._load_fonts()

        self.main_window: Optional[MainDashboard] = None
        self._update_checker: Optional[UpdateChecker] = None
        self._update_downloader: Optional[UpdateDownloader] = None
        self._pending_update: Optional[dict] = None

    def _load_fonts(self):
        """Bundle Inter and make it the app-wide UI font.

        Inter is designed for on-screen UI — its weights are evenly graded,
        so hierarchy comes from Medium/SemiBold rather than the heavy Bold
        the system font forced. Falls back silently to the system font if
        the files are missing (e.g. a stripped build).
        """
        import os
        from PyQt5.QtGui import QFontDatabase, QFont
        base = os.path.join(os.path.dirname(__file__), "resources", "fonts")
        loaded = False
        for fn in ("Inter-Regular.ttf", "Inter-Medium.ttf",
                   "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
            path = os.path.join(base, fn)
            if os.path.exists(path) and QFontDatabase.addApplicationFont(path) != -1:
                loaded = True
        if loaded:
            f = QFont("Inter")
            f.setPixelSize(13)
            self.app.setFont(f)
        self._apply_dark_theme()

    def _apply_dark_theme(self):
        """Base dark theme matched to seenslide.com. Per-widget styles layer
        on top; this catches dialogs, menus, scrollbars and any widget that
        doesn't set its own background."""
        from PyQt5.QtGui import QPalette, QColor
        pal = QPalette()
        ground = QColor("#07070a"); surface = QColor("#14141e"); text = QColor(255, 255, 255, 242)
        pal.setColor(QPalette.Window, ground)
        pal.setColor(QPalette.Base, QColor("#101019"))
        pal.setColor(QPalette.AlternateBase, surface)
        pal.setColor(QPalette.Text, text)
        pal.setColor(QPalette.WindowText, text)
        pal.setColor(QPalette.Button, surface)
        pal.setColor(QPalette.ButtonText, text)
        pal.setColor(QPalette.ToolTipBase, surface)
        pal.setColor(QPalette.ToolTipText, text)
        pal.setColor(QPalette.Highlight, QColor("#10b981"))
        pal.setColor(QPalette.HighlightedText, QColor("#06110c"))
        pal.setColor(QPalette.PlaceholderText, QColor(255, 255, 255, 102))
        self.app.setPalette(pal)
        self.app.setStyleSheet("""
            QMainWindow, QDialog, QWidget { background-color: #07070a; color: rgba(255,255,255,0.92); }
            QToolTip { background: #191922; color: #eef2f7; border: 1px solid rgba(255,255,255,0.12); padding: 5px 8px; border-radius: 6px; }
            QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,0.16); border-radius: 5px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.28); }
            QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
            QScrollBar::handle:horizontal { background: rgba(255,255,255,0.16); border-radius: 5px; min-width: 30px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
            QMenu { background: #14141e; color: #eef2f7; border: 1px solid rgba(255,255,255,0.10); border-radius: 8px; padding: 4px; }
            QMenu::item { padding: 6px 22px; border-radius: 6px; }
            QMenu::item:selected { background: rgba(16,185,129,0.18); }
            QComboBox QAbstractItemView { background: #14141e; color: #eef2f7; border: 1px solid rgba(255,255,255,0.10); selection-background-color: rgba(16,185,129,0.25); outline: none; }
        """)

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
