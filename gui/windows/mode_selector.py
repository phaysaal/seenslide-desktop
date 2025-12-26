"""Mode selector window - choose between Direct Talk and Conference Mode."""

from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QPainter, QColor
import logging

logger = logging.getLogger(__name__)


class ModeSelector(QWidget):
    """Window for selecting between Direct Talk and Conference Mode."""

    # Signals
    direct_talk_selected = pyqtSignal()
    conference_mode_selected = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize mode selector.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self._setup_ui()

        logger.info("ModeSelector initialized")

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("SeenSlide - Slide Capture")
        self.setMinimumSize(700, 500)
        self.setMaximumSize(700, 500)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(30)
        main_layout.setContentsMargins(40, 40, 40, 40)

        # Logo/Icon area
        logo_label = QLabel(self)
        logo_label.setPixmap(self._create_logo())
        logo_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(logo_label)

        # Title
        title = QLabel("SeenSlide", self)
        title.setFont(QFont("Arial", 32, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #4CAF50; margin: 0;")
        main_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Automatic Slide Capture for Presentations", self)
        subtitle.setFont(QFont("Arial", 14))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 20px;")
        main_layout.addWidget(subtitle)

        # Separator
        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #ddd;")
        main_layout.addWidget(separator)

        # Mode selection label
        mode_label = QLabel("Choose a mode:", self)
        mode_label.setFont(QFont("Arial", 16, QFont.Bold))
        mode_label.setAlignment(Qt.AlignCenter)
        mode_label.setStyleSheet("color: #333; margin-top: 10px;")
        main_layout.addWidget(mode_label)

        # Buttons layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)

        # Direct Talk button
        self.direct_talk_button = self._create_mode_button(
            "Quick Talk",
            "Start a single talk immediately\n\n"
            "• Auto-start after 10-second countdown\n"
            "• No manual server management\n"
            "• Perfect for individual presentations"
        )
        self.direct_talk_button.clicked.connect(self._on_direct_talk_clicked)
        buttons_layout.addWidget(self.direct_talk_button)

        # Conference Mode button
        self.conference_button = self._create_mode_button(
            "Conference Mode",
            "Launch admin interface for multiple talks\n\n"
            "• Manage multiple presentations\n"
            "• Full control via web interface\n"
            "• Runs in background (system tray)"
        )
        self.conference_button.clicked.connect(self._on_conference_clicked)
        buttons_layout.addWidget(self.conference_button)

        main_layout.addLayout(buttons_layout)

        # Add stretch to push everything up
        main_layout.addStretch()

        # Footer
        footer = QLabel("Select a mode to get started", self)
        footer.setFont(QFont("Arial", 11))
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999;")
        main_layout.addWidget(footer)

        self.setLayout(main_layout)

    def _create_logo(self) -> QPixmap:
        """Create application logo.

        Returns:
            QPixmap with logo
        """
        # Create 80x80 logo with "SS" text
        pixmap = QPixmap(80, 80)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw circle background
        painter.setBrush(QColor(76, 175, 80))  # Green
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 80, 80)

        # Draw "SS" text
        painter.setPen(QColor(255, 255, 255))  # White
        painter.setFont(QFont("Arial", 32, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "SS")

        painter.end()

        return pixmap

    def _create_mode_button(self, title: str, description: str) -> QPushButton:
        """Create a mode selection button.

        Args:
            title: Button title
            description: Mode description

        Returns:
            Styled QPushButton
        """
        button = QPushButton(self)
        button.setText(f"{title}\n\n{description}")
        button.setMinimumHeight(180)
        button.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 10px;
                padding: 20px;
                font-size: 13px;
                text-align: center;
                color: #333;
            }
            QPushButton:hover {
                border-color: #4CAF50;
                background-color: #f9f9f9;
            }
            QPushButton:pressed {
                background-color: #e8f5e9;
            }
        """)

        # Make title bold by using HTML
        button.setText("")
        button.setText(
            f"<div style='text-align: center;'>"
            f"<div style='font-size: 18px; font-weight: bold; color: #4CAF50; margin-bottom: 15px;'>{title}</div>"
            f"<div style='font-size: 12px; color: #666; line-height: 1.6; text-align: left;'>{description.replace(chr(10), '<br>')}</div>"
            f"</div>"
        )
        button.setTextFormat(Qt.RichText)

        return button

    def _on_direct_talk_clicked(self):
        """Handle Direct Talk button click."""
        logger.info("Direct Talk mode selected")
        self.direct_talk_selected.emit()

    def _on_conference_clicked(self):
        """Handle Conference Mode button click."""
        logger.info("Conference Mode selected")
        self.conference_mode_selected.emit()
