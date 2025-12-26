"""Countdown widget with progress circle animation."""

from typing import Optional
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
import logging

logger = logging.getLogger(__name__)


class CountdownWidget(QWidget):
    """Widget displaying countdown timer with circular progress."""

    # Signal emitted when countdown completes
    countdown_finished = pyqtSignal()

    # Signal emitted when countdown is cancelled
    countdown_cancelled = pyqtSignal()

    def __init__(
        self,
        duration: int = 10,
        title: str = "Starting in...",
        parent: Optional[QWidget] = None
    ):
        """Initialize countdown widget.

        Args:
            duration: Countdown duration in seconds (default: 10)
            title: Title text to display (default: "Starting in...")
            parent: Parent widget
        """
        super().__init__(parent)

        self.duration = duration
        self.remaining = duration
        self.title_text = title

        # Timer for countdown
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)

        # Setup UI
        self._setup_ui()

        logger.info(f"CountdownWidget initialized: {duration}s")

    def _setup_ui(self):
        """Setup the UI components."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Title label
        self.title_label = QLabel(self.title_text, self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #333;
                margin-bottom: 20px;
            }
        """)
        layout.addWidget(self.title_label)

        # Countdown display (will be drawn in paintEvent)
        self.countdown_display = QWidget(self)
        self.countdown_display.setFixedSize(200, 200)
        layout.addWidget(self.countdown_display, alignment=Qt.AlignCenter)

        # Cancel button
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 10px 30px;
                font-size: 14px;
                border-radius: 5px;
                margin-top: 20px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        self.cancel_button.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def paintEvent(self, event):
        """Paint the countdown circle."""
        super().paintEvent(event)

        # Only paint if countdown_display exists and is visible
        if not hasattr(self, 'countdown_display'):
            return

        # Calculate progress (0.0 to 1.0)
        progress = 1.0 - (self.remaining / self.duration) if self.duration > 0 else 1.0

        # Create painter
        painter = QPainter(self.countdown_display)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.countdown_display.width()
        height = self.countdown_display.height()
        size = min(width, height)

        # Center the circle
        x = (width - size) // 2
        y = (height - size) // 2
        rect = QRectF(x + 10, y + 10, size - 20, size - 20)

        # Draw background circle (gray)
        pen = QPen(QColor(200, 200, 200), 8)
        painter.setPen(pen)
        painter.drawEllipse(rect)

        # Draw progress arc (green)
        pen = QPen(QColor(76, 175, 80), 8)  # Green color
        painter.setPen(pen)

        # Arc spans 360 degrees, starts at top (90 degrees)
        start_angle = 90 * 16  # Qt uses 1/16th degree units
        span_angle = -int(progress * 360 * 16)  # Negative for clockwise
        painter.drawArc(rect, start_angle, span_angle)

        # Draw remaining seconds in center
        font = QFont("Arial", 48, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(51, 51, 51))  # Dark gray text
        painter.drawText(rect, Qt.AlignCenter, str(self.remaining))

    def start(self):
        """Start the countdown."""
        logger.info(f"Starting countdown: {self.duration}s")
        self.remaining = self.duration
        self.timer.start(1000)  # Tick every second
        self.update()

    def stop(self):
        """Stop the countdown."""
        logger.info("Stopping countdown")
        self.timer.stop()

    def _on_timer_tick(self):
        """Handle timer tick (every second)."""
        self.remaining -= 1
        logger.debug(f"Countdown: {self.remaining}s remaining")

        # Update display
        self.update()

        # Check if finished
        if self.remaining <= 0:
            self.timer.stop()
            logger.info("Countdown finished")
            self.countdown_finished.emit()

    def _on_cancel(self):
        """Handle cancel button click."""
        logger.info("Countdown cancelled by user")
        self.stop()
        self.countdown_cancelled.emit()

    def set_title(self, title: str):
        """Update the title text.

        Args:
            title: New title text
        """
        self.title_text = title
        if hasattr(self, 'title_label'):
            self.title_label.setText(title)

    def reset(self):
        """Reset countdown to initial duration."""
        self.stop()
        self.remaining = self.duration
        self.update()
