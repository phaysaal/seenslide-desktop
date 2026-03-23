"""Non-intrusive animated banner for update notifications and broadcast messages."""

import logging
import subprocess
import platform
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont

logger = logging.getLogger(__name__)

BANNER_H = 44  # Expanded height (px)


class UpdateBanner(QWidget):
    """Slim animated notification bar.

    Sits hidden (0 height) inside the main layout and slides open when
    an update or broadcast message arrives.

    Signals:
        download_requested(dict):  User clicked "Download" — carries update info.
        install_requested(str):    User clicked "Install & Restart" — carries file path.
        dismiss_requested(str):    User dismissed a message — carries message id.
    """

    download_requested = pyqtSignal(dict)
    install_requested = pyqtSignal(str)
    dismiss_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._info: Dict[str, Any] = {}
        self._downloaded_path: Optional[str] = None
        self._anim: Optional[QPropertyAnimation] = None
        self._build_ui()
        # Start collapsed
        self.setMaximumHeight(0)
        self.hide()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Container with background styling
        self._container = QWidget(self)

        inner = QHBoxLayout(self._container)
        inner.setContentsMargins(14, 6, 14, 6)
        inner.setSpacing(10)

        # Status dot
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        inner.addWidget(self._dot, 0, Qt.AlignVCenter)

        # Text
        self._text = QLabel()
        self._text.setFont(QFont("Arial", 10))
        self._text.setWordWrap(False)
        inner.addWidget(self._text, 1)

        # Progress bar (hidden until downloading)
        self._progress = QProgressBar()
        self._progress.setFixedWidth(100)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: rgba(37, 99, 235, 0.1);
                border: none; border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #2563eb; border-radius: 3px;
            }
        """)
        self._progress.hide()
        inner.addWidget(self._progress, 0, Qt.AlignVCenter)

        # Action button
        self._action = QPushButton()
        self._action.setFont(QFont("Arial", 9, QFont.Bold))
        self._action.setCursor(Qt.PointingHandCursor)
        self._action.clicked.connect(self._on_action)
        inner.addWidget(self._action, 0, Qt.AlignVCenter)

        # Dismiss button
        self._dismiss = QPushButton("\u00d7")  # ×
        self._dismiss.setFixedSize(22, 22)
        self._dismiss.setCursor(Qt.PointingHandCursor)
        self._dismiss.setFont(QFont("Arial", 13))
        self._dismiss.setStyleSheet("""
            QPushButton {
                background: transparent; color: #94a3b8;
                border: none; border-radius: 11px; padding: 0;
            }
            QPushButton:hover { color: #475569; background: rgba(15,23,42,0.05); }
        """)
        self._dismiss.clicked.connect(self._on_dismiss)
        inner.addWidget(self._dismiss, 0, Qt.AlignVCenter)

        # Outer layout with horizontal margins matching mode-selector cards
        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 2, 20, 2)
        outer.addWidget(self._container)

        # Apply default (blue / info) styling
        self._apply_theme("info")

    # ------------------------------------------------------------------
    # Theme helpers
    # ------------------------------------------------------------------

    _THEMES = {
        "info": {
            "dot": "#2563eb",
            "text": "#1e40af",
            "bg": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #eff6ff, stop:1 #f0f9ff)",
            "border": "rgba(37,99,235,0.15)",
            "btn_bg": "#2563eb", "btn_hover": "#1d4ed8",
        },
        "warning": {
            "dot": "#f59e0b",
            "text": "#92400e",
            "bg": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #fffbeb, stop:1 #fefce8)",
            "border": "rgba(245,158,11,0.2)",
            "btn_bg": "#f59e0b", "btn_hover": "#d97706",
        },
        "critical": {
            "dot": "#ef4444",
            "text": "#991b1b",
            "bg": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #fef2f2, stop:1 #fff1f2)",
            "border": "rgba(239,68,68,0.2)",
            "btn_bg": "#ef4444", "btn_hover": "#dc2626",
        },
        "success": {
            "dot": "#16a34a",
            "text": "#166534",
            "bg": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f0fdf4, stop:1 #ecfdf5)",
            "border": "rgba(22,163,74,0.2)",
            "btn_bg": "#16a34a", "btn_hover": "#15803d",
        },
    }

    def _apply_theme(self, name: str):
        t = self._THEMES.get(name, self._THEMES["info"])
        self._dot.setStyleSheet(
            f"background: {t['dot']}; border-radius: 4px;"
        )
        self._text.setStyleSheet(
            f"color: {t['text']}; background: transparent; border: none;"
        )
        self._container.setStyleSheet(
            f"background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 10px;"
        )
        self._action.setStyleSheet(f"""
            QPushButton {{
                background: {t['btn_bg']}; color: white;
                border: none; border-radius: 6px; padding: 4px 12px;
            }}
            QPushButton:hover {{ background: {t['btn_hover']}; }}
        """)

    # ------------------------------------------------------------------
    # Public API — show different states
    # ------------------------------------------------------------------

    def show_update(self, info: dict):
        """Show 'new version available' banner."""
        self._info = info
        self._downloaded_path = None
        version = info.get("version", "?")

        self._apply_theme("critical" if info.get("is_critical") else "info")
        self._text.setText(f"v{version} available")
        self._action.setText("Download")
        self._action.show()
        self._progress.hide()
        self._dismiss.show()
        self._slide_open()

    def show_message(self, msg: dict):
        """Show a broadcast message banner."""
        self._info = msg
        self._downloaded_path = None
        msg_type = msg.get("type", "info")

        display = msg.get("title") or msg.get("body", "")
        if len(display) > 65:
            display = display[:62] + "..."

        self._apply_theme(msg_type if msg_type in self._THEMES else "info")
        self._text.setText(display)

        action_url = msg.get("action_url")
        action_text = msg.get("action_text")
        if action_url and action_text:
            self._action.setText(action_text)
            self._action.show()
        else:
            self._action.hide()

        self._dismiss.setVisible(msg.get("dismissible", True))
        self._slide_open()

    def set_download_progress(self, downloaded: int, total: int):
        """Update the progress bar during a download."""
        self._progress.show()
        self._action.hide()
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(downloaded)
            mb_done = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self._text.setText(f"Downloading... {mb_done:.1f} / {mb_total:.1f} MB")
        else:
            self._progress.setMaximum(0)
            self._text.setText(f"Downloading... {downloaded / (1024*1024):.1f} MB")

    def set_download_complete(self, file_path: str):
        """Show 'ready to install' state."""
        self._downloaded_path = file_path
        self._progress.hide()
        self._apply_theme("success")
        self._text.setText("Update ready to install")
        self._action.setText("Install & Restart")
        self._action.show()

    def set_download_failed(self, error: str):
        """Show download failure with retry."""
        self._progress.hide()
        self._apply_theme("warning")
        short = error if len(error) < 50 else error[:47] + "..."
        self._text.setText(f"Download failed: {short}")
        self._action.setText("Retry")
        self._action.show()

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _slide_open(self):
        self.show()
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(250)
        self._anim.setStartValue(self.maximumHeight())
        self._anim.setEndValue(BANNER_H)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def _slide_closed(self):
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setStartValue(self.maximumHeight())
        self._anim.setEndValue(0)
        self._anim.setEasingCurve(QEasingCurve.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_action(self):
        if self._downloaded_path:
            self.install_requested.emit(self._downloaded_path)
            return

        # Message with action URL → open browser
        action_url = self._info.get("action_url")
        if action_url:
            webbrowser.open(action_url)
            return

        # Update download
        if self._info.get("download_url"):
            self.download_requested.emit(self._info)
            return

    def _on_dismiss(self):
        msg_id = self._info.get("id", "")
        if msg_id:
            self.dismiss_requested.emit(msg_id)
        self._slide_closed()

    # ------------------------------------------------------------------
    # Install helper
    # ------------------------------------------------------------------

    @staticmethod
    def launch_installer(file_path: str):
        """Open / execute the downloaded update artifact.

        - AppImage / .run → replace-in-place or execute
        - .deb            → xdg-open (opens in Software Center)
        - .exe / .msi     → subprocess.Popen
        - .dmg            → open (macOS)
        """
        system = platform.system()
        path = file_path

        if system == "Linux":
            if path.endswith(".deb"):
                subprocess.Popen(["xdg-open", path])
            else:
                # AppImage or generic binary — open containing folder
                subprocess.Popen(["xdg-open", str(Path(path).parent)])
        elif system == "Windows":
            subprocess.Popen([path], shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
