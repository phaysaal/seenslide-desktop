"""Mode selector window - choose between Direct Talk and Conference Mode."""

from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QToolButton
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
        self.direct_talk_button = self._create_mode_card(
            "Quick Talk",
            "Start a single talk immediately",
            [
                "Auto-start after 10-second countdown",
                "No manual server management",
                "Perfect for individual presentations"
            ]
        )
        buttons_layout.addWidget(self.direct_talk_button)

        # Conference Mode button
        self.conference_button = self._create_mode_card(
            "Conference Mode",
            "Launch admin interface for multiple talks",
            [
                "Manage multiple presentations",
                "Full control via web interface",
                "Runs in background (system tray)"
            ]
        )
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

    def _create_mode_card(self, title: str, subtitle: str, points: list) -> QPushButton:
        """Create a mode selection card.

        Args:
            title: Card title
            subtitle: Card subtitle
            points: List of bullet points

        Returns:
            Clickable QPushButton styled as a card
        """
        button = QPushButton(self)
        button.setMinimumHeight(180)
        button.setCursor(Qt.PointingHandCursor)

        # Create layout for button content
        layout = QVBoxLayout(button)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setStyleSheet("color: #4CAF50;")
        title_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel(subtitle)
        subtitle_label.setFont(QFont("Arial", 11))
        subtitle_label.setStyleSheet("color: #666;")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        # Spacer
        layout.addSpacing(10)

        # Bullet points
        for point in points:
            point_label = QLabel(f"• {point}")
            point_label.setFont(QFont("Arial", 10))
            point_label.setStyleSheet("color: #555;")
            point_label.setWordWrap(True)
            layout.addWidget(point_label)

        # Add stretch to push content to top
        layout.addStretch()

        # Style the button
        button.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 10px;
                text-align: left;
            }
            QPushButton:hover {
                border-color: #4CAF50;
                background-color: #f9f9f9;
            }
            QPushButton:pressed {
                background-color: #e8f5e9;
                border-color: #45a049;
            }
        """)

        # Connect click based on which button
        if "Quick" in title or "Direct" in title:
            button.clicked.connect(self._on_direct_talk_clicked)
        else:
            button.clicked.connect(self._on_conference_clicked)

        return button

    def _on_direct_talk_clicked(self):
        """Handle Direct Talk button click."""
        logger.info("Direct Talk mode selected")
        self.direct_talk_selected.emit()

    def _on_conference_clicked(self):
        """Handle Conference Mode button click."""
        logger.info("Conference Mode selected")
        self.conference_mode_selected.emit()
