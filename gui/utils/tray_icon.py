"""System tray integration for SeenSlide."""

from typing import Optional, Callable
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import pyqtSignal, QObject
import logging

logger = logging.getLogger(__name__)


class TrayIcon(QObject):
    """System tray icon with menu for server management."""

    # Signals
    restore_requested = pyqtSignal()
    stop_server_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        """Initialize tray icon.

        Args:
            parent: Parent QObject
        """
        super().__init__(parent)

        # Create system tray icon
        self.tray = QSystemTrayIcon(parent)
        self.tray.setIcon(self._create_icon())
        self.tray.setToolTip("SeenSlide - Slide Capture Server")

        # Create menu
        self.menu = QMenu()
        self._create_menu()
        self.tray.setContextMenu(self.menu)

        # Connect activated signal (double-click, etc.)
        self.tray.activated.connect(self._on_activated)

        logger.info("TrayIcon initialized")

    def _create_icon(self) -> QIcon:
        """Create application icon.

        Returns:
            QIcon for system tray
        """
        # Create a simple icon (32x32 with "SS" text)
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(76, 175, 80))  # Green background

        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))  # White text
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.drawText(pixmap.rect(), 0x84, "SS")  # AlignCenter
        painter.end()

        return QIcon(pixmap)

    def _create_menu(self):
        """Create context menu."""
        # Restore action
        self.restore_action = QAction("Restore Window", self.menu)
        self.restore_action.triggered.connect(self._on_restore)
        self.menu.addAction(self.restore_action)

        # Separator
        self.menu.addSeparator()

        # Stop server action
        self.stop_action = QAction("Stop Server", self.menu)
        self.stop_action.triggered.connect(self._on_stop_server)
        self.menu.addAction(self.stop_action)

        # Separator
        self.menu.addSeparator()

        # Quit action
        self.quit_action = QAction("Quit", self.menu)
        self.quit_action.triggered.connect(self._on_quit)
        self.menu.addAction(self.quit_action)

    def _on_activated(self, reason):
        """Handle tray icon activation.

        Args:
            reason: Activation reason (DoubleClick, Trigger, etc.)
        """
        if reason == QSystemTrayIcon.DoubleClick:
            logger.info("Tray icon double-clicked, restoring window")
            self.restore_requested.emit()

    def _on_restore(self):
        """Handle restore action."""
        logger.info("Restore requested from tray menu")
        self.restore_requested.emit()

    def _on_stop_server(self):
        """Handle stop server action."""
        logger.info("Stop server requested from tray menu")
        self.stop_server_requested.emit()

    def _on_quit(self):
        """Handle quit action."""
        logger.info("Quit requested from tray menu")
        self.quit_requested.emit()

    def show(self):
        """Show the tray icon."""
        logger.info("Showing tray icon")
        self.tray.show()

    def hide(self):
        """Hide the tray icon."""
        logger.info("Hiding tray icon")
        self.tray.hide()

    def show_message(self, title: str, message: str, icon=QSystemTrayIcon.Information, duration: int = 3000):
        """Show a notification message.

        Args:
            title: Message title
            message: Message body
            icon: Icon type (Information, Warning, Critical)
            duration: Display duration in milliseconds
        """
        logger.info(f"Showing tray message: {title} - {message}")
        self.tray.showMessage(title, message, icon, duration)

    def set_tooltip(self, tooltip: str):
        """Set tray icon tooltip.

        Args:
            tooltip: Tooltip text
        """
        self.tray.setToolTip(tooltip)

    def enable_stop_action(self, enabled: bool):
        """Enable or disable the stop server action.

        Args:
            enabled: True to enable, False to disable
        """
        self.stop_action.setEnabled(enabled)

    def is_visible(self) -> bool:
        """Check if tray icon is visible.

        Returns:
            True if visible, False otherwise
        """
        return self.tray.isVisible()
