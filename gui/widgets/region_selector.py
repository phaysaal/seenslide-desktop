"""Region selector widget with draggable rectangle overlay."""

from typing import Optional, Dict, Tuple, Callable
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QApplication, QDesktopWidget
)
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QPixmap, QImage, QPalette, QCursor
)
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class RegionSelector(QWidget):
    """Fullscreen overlay widget for selecting a screen region."""

    # Signal emitted when region is confirmed (region dict)
    region_confirmed = pyqtSignal(dict)

    # Signal emitted when selection is cancelled
    selection_cancelled = pyqtSignal()

    def __init__(
        self,
        screenshot: Image.Image,
        default_region: Dict[str, int],
        parent: Optional[QWidget] = None
    ):
        """Initialize region selector.

        Args:
            screenshot: PIL Image of the screen to overlay
            default_region: Default region dict with x, y, width, height
            parent: Parent widget
        """
        super().__init__(parent)

        self.screenshot = screenshot
        self.screen_width = screenshot.width
        self.screen_height = screenshot.height

        # Region being selected
        self.region = QRect(
            default_region['x'],
            default_region['y'],
            default_region['width'],
            default_region['height']
        )

        # Mouse interaction state
        self.dragging = False
        self.resizing = False
        self.resize_edge = None  # 'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', or None
        self.drag_start_pos = QPoint()
        self.drag_start_region = QRect()

        # Resize handle size
        self.handle_size = 10

        # Setup UI
        self._setup_ui()

        logger.info(f"RegionSelector initialized: {self.screen_width}x{self.screen_height}")
        logger.info(f"Default region: {default_region}")

    def _setup_ui(self):
        """Setup the UI components."""
        # Make fullscreen and frameless
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Set window to fullscreen
        screen = QDesktopWidget().screenGeometry()
        self.setGeometry(screen)

        # Convert PIL image to QPixmap for display
        self.background_pixmap = self._pil_to_qpixmap(self.screenshot)

        # Create info panel
        self._create_info_panel()

        # Set mouse tracking to detect hover over edges
        self.setMouseTracking(True)

        # Show fullscreen
        self.showFullScreen()

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap.

        Args:
            pil_image: PIL Image to convert

        Returns:
            QPixmap for display
        """
        # Convert PIL image to RGB if needed
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        # Get image data
        data = pil_image.tobytes('raw', 'RGB')
        qimage = QImage(
            data,
            pil_image.width,
            pil_image.height,
            pil_image.width * 3,
            QImage.Format_RGB888
        )

        return QPixmap.fromImage(qimage)

    def _create_info_panel(self):
        """Create info panel showing coordinates and controls."""
        # Info label showing current region
        self.info_label = QLabel(self)
        self.info_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
        """)
        self.info_label.setAlignment(Qt.AlignCenter)
        self._update_info_label()

        # Position info label at top center
        self.info_label.move(
            (self.screen_width - self.info_label.width()) // 2,
            20
        )

        # Create button panel
        button_widget = QWidget(self)
        button_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
                border-radius: 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 14px;
                border-radius: 3px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton#cancel {
                background-color: #f44336;
            }
            QPushButton#cancel:hover {
                background-color: #da190b;
            }
        """)

        # Create buttons
        confirm_btn = QPushButton("Confirm", button_widget)
        confirm_btn.clicked.connect(self._on_confirm)

        cancel_btn = QPushButton("Cancel", button_widget)
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self._on_cancel)

        # Layout buttons horizontally
        button_layout = QHBoxLayout(button_widget)
        button_layout.addWidget(confirm_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.setContentsMargins(10, 10, 10, 10)
        button_widget.setLayout(button_layout)

        # Position button panel at bottom center
        button_widget.adjustSize()
        button_widget.move(
            (self.screen_width - button_widget.width()) // 2,
            self.screen_height - button_widget.height() - 20
        )

    def _update_info_label(self):
        """Update info label with current region coordinates."""
        text = (
            f"Position: ({self.region.x()}, {self.region.y()})  |  "
            f"Size: {self.region.width()}x{self.region.height()}  |  "
            f"Bounds: ({self.region.x() + self.region.width()}, {self.region.y() + self.region.height()})"
        )
        self.info_label.setText(text)
        self.info_label.adjustSize()

    def paintEvent(self, event):
        """Paint the overlay with screenshot and selection rectangle."""
        painter = QPainter(self)

        # Draw screenshot
        painter.drawPixmap(0, 0, self.background_pixmap)

        # Draw semi-transparent dark overlay on non-selected area
        overlay_color = QColor(0, 0, 0, 120)

        # Draw overlay in 4 rectangles around the selection
        # Top
        if self.region.y() > 0:
            painter.fillRect(0, 0, self.screen_width, self.region.y(), overlay_color)

        # Bottom
        bottom_y = self.region.y() + self.region.height()
        if bottom_y < self.screen_height:
            painter.fillRect(
                0, bottom_y,
                self.screen_width, self.screen_height - bottom_y,
                overlay_color
            )

        # Left
        if self.region.x() > 0:
            painter.fillRect(
                0, self.region.y(),
                self.region.x(), self.region.height(),
                overlay_color
            )

        # Right
        right_x = self.region.x() + self.region.width()
        if right_x < self.screen_width:
            painter.fillRect(
                right_x, self.region.y(),
                self.screen_width - right_x, self.region.height(),
                overlay_color
            )

        # Draw selection rectangle border
        pen = QPen(QColor(0, 255, 0), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(self.region)

        # Draw resize handles (small squares at corners and edges)
        handle_color = QColor(0, 255, 0)
        painter.fillRect(self._get_handle_rect('nw'), handle_color)
        painter.fillRect(self._get_handle_rect('ne'), handle_color)
        painter.fillRect(self._get_handle_rect('sw'), handle_color)
        painter.fillRect(self._get_handle_rect('se'), handle_color)
        painter.fillRect(self._get_handle_rect('n'), handle_color)
        painter.fillRect(self._get_handle_rect('s'), handle_color)
        painter.fillRect(self._get_handle_rect('e'), handle_color)
        painter.fillRect(self._get_handle_rect('w'), handle_color)

    def _get_handle_rect(self, edge: str) -> QRect:
        """Get the rectangle for a resize handle.

        Args:
            edge: Edge identifier ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw')

        Returns:
            QRect for the handle
        """
        hs = self.handle_size
        x, y, w, h = self.region.x(), self.region.y(), self.region.width(), self.region.height()

        if edge == 'nw':
            return QRect(x - hs // 2, y - hs // 2, hs, hs)
        elif edge == 'ne':
            return QRect(x + w - hs // 2, y - hs // 2, hs, hs)
        elif edge == 'sw':
            return QRect(x - hs // 2, y + h - hs // 2, hs, hs)
        elif edge == 'se':
            return QRect(x + w - hs // 2, y + h - hs // 2, hs, hs)
        elif edge == 'n':
            return QRect(x + w // 2 - hs // 2, y - hs // 2, hs, hs)
        elif edge == 's':
            return QRect(x + w // 2 - hs // 2, y + h - hs // 2, hs, hs)
        elif edge == 'e':
            return QRect(x + w - hs // 2, y + h // 2 - hs // 2, hs, hs)
        elif edge == 'w':
            return QRect(x - hs // 2, y + h // 2 - hs // 2, hs, hs)

        return QRect()

    def _get_edge_at_pos(self, pos: QPoint) -> Optional[str]:
        """Get which edge/handle is at the given position.

        Args:
            pos: Mouse position

        Returns:
            Edge identifier or None
        """
        for edge in ['nw', 'ne', 'sw', 'se', 'n', 's', 'e', 'w']:
            if self._get_handle_rect(edge).contains(pos):
                return edge
        return None

    def _update_cursor(self, edge: Optional[str]):
        """Update cursor based on which edge is being hovered.

        Args:
            edge: Edge identifier or None
        """
        if edge in ['nw', 'se']:
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge in ['ne', 'sw']:
            self.setCursor(Qt.SizeBDiagCursor)
        elif edge in ['n', 's']:
            self.setCursor(Qt.SizeVerCursor)
        elif edge in ['e', 'w']:
            self.setCursor(Qt.SizeHorCursor)
        elif self.region.contains(edge or QPoint()):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        """Handle mouse press for dragging or resizing."""
        if event.button() == Qt.LeftButton:
            pos = event.pos()

            # Check if clicking on a resize handle
            edge = self._get_edge_at_pos(pos)
            if edge:
                self.resizing = True
                self.resize_edge = edge
                self.drag_start_pos = pos
                self.drag_start_region = QRect(self.region)
                logger.debug(f"Started resizing from edge: {edge}")
            elif self.region.contains(pos):
                # Start dragging
                self.dragging = True
                self.drag_start_pos = pos
                self.drag_start_region = QRect(self.region)
                logger.debug("Started dragging region")

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging, resizing, or cursor update."""
        pos = event.pos()

        if self.resizing:
            # Calculate delta
            delta = pos - self.drag_start_pos

            # Update region based on resize edge
            new_region = QRect(self.drag_start_region)

            if 'n' in self.resize_edge:
                new_region.setTop(self.drag_start_region.top() + delta.y())
            if 's' in self.resize_edge:
                new_region.setBottom(self.drag_start_region.bottom() + delta.y())
            if 'e' in self.resize_edge:
                new_region.setRight(self.drag_start_region.right() + delta.x())
            if 'w' in self.resize_edge:
                new_region.setLeft(self.drag_start_region.left() + delta.x())

            # Ensure minimum size
            if new_region.width() >= 100 and new_region.height() >= 100:
                # Ensure within screen bounds
                if (new_region.x() >= 0 and new_region.y() >= 0 and
                    new_region.right() < self.screen_width and
                    new_region.bottom() < self.screen_height):
                    self.region = new_region
                    self._update_info_label()
                    self.update()

        elif self.dragging:
            # Calculate delta
            delta = pos - self.drag_start_pos

            # Move region
            new_x = self.drag_start_region.x() + delta.x()
            new_y = self.drag_start_region.y() + delta.y()

            # Ensure within screen bounds
            new_x = max(0, min(new_x, self.screen_width - self.region.width()))
            new_y = max(0, min(new_y, self.screen_height - self.region.height()))

            self.region.moveTo(new_x, new_y)
            self._update_info_label()
            self.update()

        else:
            # Update cursor based on hover position
            edge = self._get_edge_at_pos(pos)
            if edge:
                self._update_cursor(edge)
            elif self.region.contains(pos):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging or resizing."""
        if event.button() == Qt.LeftButton:
            if self.dragging:
                logger.debug(f"Stopped dragging: {self.region}")
                self.dragging = False
            elif self.resizing:
                logger.debug(f"Stopped resizing: {self.region}")
                self.resizing = False
                self.resize_edge = None

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Escape:
            self._on_cancel()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_confirm()

    def _on_confirm(self):
        """Handle confirm button click."""
        region_dict = {
            'x': self.region.x(),
            'y': self.region.y(),
            'width': self.region.width(),
            'height': self.region.height()
        }
        logger.info(f"Region confirmed: {region_dict}")
        self.region_confirmed.emit(region_dict)
        self.close()

    def _on_cancel(self):
        """Handle cancel button or Escape key."""
        logger.info("Region selection cancelled")
        self.selection_cancelled.emit()
        self.close()

    def get_region_dict(self) -> Dict[str, int]:
        """Get current region as dictionary.

        Returns:
            Region dictionary with x, y, width, height
        """
        return {
            'x': self.region.x(),
            'y': self.region.y(),
            'width': self.region.width(),
            'height': self.region.height()
        }
