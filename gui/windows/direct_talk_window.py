"""Direct Talk Mode window."""

from typing import Optional, Dict
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QSlider, QComboBox, QGroupBox,
    QMessageBox, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
import logging

from gui.widgets.countdown_widget import CountdownWidget
from gui.widgets.region_selector import RegionSelector
from gui.utils.server_manager import ServerManager
from gui.utils.screenshot_util import capture_screenshot, get_primary_screen_size, get_monitor_count
from gui.utils.region_utils import calculate_default_region
from gui.utils.portal_session import PortalSessionManager

logger = logging.getLogger(__name__)


class DirectTalkWindow(QWidget):
    """Window for Direct Talk mode with auto-start."""

    # Signal emitted when talk is stopped
    talk_stopped = pyqtSignal()

    # Signal emitted when window should close
    close_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize Direct Talk window.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Server manager
        self.server_manager = ServerManager()

        # Selected region (default to 50% center)
        width, height = get_primary_screen_size()
        self.crop_region = calculate_default_region(width, height, 0.5)

        # Talk session
        self.session_id: Optional[str] = None
        self.is_active = False
        self.server_started = False

        # Status polling timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_status)

        # Setup UI
        self._setup_ui()

        # Start idle orchestrator after window shows
        QTimer.singleShot(500, self._start_idle_server)

        logger.info("DirectTalkWindow initialized")

    def _setup_ui(self):
        """Setup the UI components."""
        self.setWindowTitle("SeenSlide - Direct Talk Mode")
        self.setMinimumSize(600, 700)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Quick Talk Setup", self)
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # Talk metadata group
        metadata_group = self._create_metadata_group()
        main_layout.addWidget(metadata_group)

        # Capture settings group
        settings_group = self._create_settings_group()
        main_layout.addWidget(settings_group)

        # Region info (no manual selection - using 50% default)
        region_info = self._create_region_info()
        main_layout.addWidget(region_info)

        # Countdown widget (hidden initially)
        self.countdown_widget = CountdownWidget(duration=10, title="Talk starting in...")
        self.countdown_widget.countdown_finished.connect(self._start_talk)
        self.countdown_widget.countdown_cancelled.connect(self._on_countdown_cancelled)
        self.countdown_widget.setVisible(False)
        main_layout.addWidget(self.countdown_widget)

        # Status display (hidden initially)
        self.status_group = self._create_status_group()
        self.status_group.setVisible(False)
        main_layout.addWidget(self.status_group)

        # Action buttons
        button_layout = QHBoxLayout()

        self.start_button = QPushButton("Start Talk", self)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 16px;
                border-radius: 5px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_button.clicked.connect(self._on_start_clicked)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Talk", self)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 16px;
                border-radius: 5px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        self.stop_button.clicked.connect(self._stop_talk)
        self.stop_button.setVisible(False)
        button_layout.addWidget(self.stop_button)

        main_layout.addLayout(button_layout)

        # Add stretch to push everything to top
        main_layout.addStretch()

        self.setLayout(main_layout)

    def _create_metadata_group(self) -> QGroupBox:
        """Create talk metadata group.

        Returns:
            QGroupBox with metadata fields
        """
        group = QGroupBox("Talk Information", self)
        layout = QVBoxLayout()

        # Talk name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Talk Title:", self))
        self.talk_name_input = QLineEdit(self)
        self.talk_name_input.setPlaceholderText("e.g., Machine Learning Basics")
        name_layout.addWidget(self.talk_name_input)
        layout.addLayout(name_layout)

        # Presenter name
        presenter_layout = QHBoxLayout()
        presenter_layout.addWidget(QLabel("Presenter:", self))
        self.presenter_input = QLineEdit(self)
        self.presenter_input.setPlaceholderText("e.g., John Doe")
        presenter_layout.addWidget(self.presenter_input)
        layout.addLayout(presenter_layout)

        # Description
        layout.addWidget(QLabel("Description (optional):", self))
        self.description_input = QTextEdit(self)
        self.description_input.setPlaceholderText("Brief description of the talk...")
        self.description_input.setMaximumHeight(80)
        layout.addWidget(self.description_input)

        group.setLayout(layout)
        return group

    def _create_settings_group(self) -> QGroupBox:
        """Create capture settings group.

        Returns:
            QGroupBox with capture settings
        """
        group = QGroupBox("Capture Settings", self)
        layout = QVBoxLayout()

        # Monitor selection
        monitor_layout = QHBoxLayout()
        monitor_layout.addWidget(QLabel("Monitor:", self))
        self.monitor_combo = QComboBox(self)

        # Populate monitors
        monitor_count = get_monitor_count()
        for i in range(1, monitor_count + 1):
            self.monitor_combo.addItem(f"Monitor {i}", i)

        monitor_layout.addWidget(self.monitor_combo)
        monitor_layout.addStretch()
        layout.addLayout(monitor_layout)

        # Deduplication tolerance
        tolerance_layout = QVBoxLayout()
        tolerance_label_row = QHBoxLayout()
        tolerance_label_row.addWidget(QLabel("Deduplication Sensitivity:", self))
        self.tolerance_value_label = QLabel("50%", self)
        tolerance_label_row.addWidget(self.tolerance_value_label)
        tolerance_label_row.addStretch()
        tolerance_layout.addLayout(tolerance_label_row)

        self.tolerance_slider = QSlider(Qt.Horizontal, self)
        self.tolerance_slider.setMinimum(0)
        self.tolerance_slider.setMaximum(100)
        self.tolerance_slider.setValue(50)
        self.tolerance_slider.setTickPosition(QSlider.TicksBelow)
        self.tolerance_slider.setTickInterval(10)
        self.tolerance_slider.valueChanged.connect(self._on_tolerance_changed)
        tolerance_layout.addWidget(self.tolerance_slider)

        help_label = QLabel("Lower = more sensitive (captures minor changes)", self)
        help_label.setStyleSheet("color: #666; font-size: 11px;")
        tolerance_layout.addWidget(help_label)

        layout.addLayout(tolerance_layout)

        group.setLayout(layout)
        return group

    def _create_region_info(self) -> QGroupBox:
        """Create region info display (no manual selection).

        Returns:
            QGroupBox with region information
        """
        group = QGroupBox("Capture Region", self)
        layout = QVBoxLayout()

        # Info label
        info_label = QLabel(
            "Using default region: 50% of screen (centered)\n"
            "Full screen will be captured, but only this region is compared for slide changes.",
            self
        )
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Region display
        self.region_display = QLabel("Calculating region...", self)
        self.region_display.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 3px;
                color: #333;
            }
        """)
        layout.addWidget(self.region_display)

        group.setLayout(layout)
        return group

    def _create_status_group(self) -> QGroupBox:
        """Create status display group.

        Returns:
            QGroupBox with live statistics
        """
        group = QGroupBox("Live Statistics", self)
        layout = QVBoxLayout()

        self.status_label = QLabel("Initializing...", self)
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.status_label)

        group.setLayout(layout)
        return group

    def _on_tolerance_changed(self, value: int):
        """Handle tolerance slider change.

        Args:
            value: Slider value (0-100)
        """
        self.tolerance_value_label.setText(f"{value}%")

    def _start_idle_server(self):
        """Start idle orchestrator in background."""
        logger.info("Starting idle orchestrator for Direct Talk mode...")

        try:
            # Start admin server
            logger.info("Starting admin server...")
            success = self.server_manager.start_server()

            if not success:
                raise Exception("Failed to start admin server")

            # Login
            logger.info("Logging in...")
            success = self.server_manager.login("admin", "admin123")

            if not success:
                raise Exception("Failed to login to admin server")

            # Set crop region (default 50% center)
            logger.info(f"Setting default crop region: {self.crop_region}")
            success = self.server_manager.set_crop_region(self.crop_region)

            if not success:
                raise Exception("Failed to set crop region")

            self.server_started = True
            logger.info("✅ Idle server started successfully")

            # Update region display
            self._update_region_display()

        except Exception as e:
            logger.error(f"Failed to start idle server: {e}")
            QMessageBox.critical(
                self,
                "Server Start Failed",
                f"Could not start idle server:\n{str(e)}\n\n"
                "Direct Talk mode requires the server to be running.\n"
                "Please restart the application."
            )
            self.close_requested.emit()

    def _select_region(self):
        """Open region selector."""
        logger.info("Opening region selector...")

        if not self.server_started:
            QMessageBox.warning(
                self,
                "Server Not Ready",
                "Please wait for the server to start before selecting a region."
            )
            return

        # Capture screenshot (will trigger portal dialog if needed)
        monitor_id = self.monitor_combo.currentData()
        screenshot = capture_screenshot(monitor_id)

        if screenshot is None:
            logger.warning("Failed to capture screenshot for region selection")

            reply = QMessageBox.warning(
                self,
                "Screenshot Failed",
                "Could not capture screenshot for region selection.\n\n"
                "This could be due to:\n"
                "• Screen capture permission denied\n"
                "• X11/Wayland configuration issues\n"
                "• Display server problems\n\n"
                "Would you like to use the default region (50% center) instead?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                # Set default region
                width, height = get_primary_screen_size()
                self.crop_region = calculate_default_region(width, height, 0.5)
                self._update_region_display()
                logger.info(f"Using default crop region: {self.crop_region}")
            return

        # Calculate default region (50% center)
        width, height = screenshot.width, screenshot.height
        default_region = self.crop_region or calculate_default_region(width, height, 0.5)

        # Create and show region selector
        selector = RegionSelector(
            screenshot=screenshot,
            default_region=default_region,
            parent=self
        )

        def on_confirmed(region):
            self.crop_region = region
            self._update_region_display()
            logger.info(f"Region selected: {region}")

            # Update server's crop region
            if self.server_started:
                success = self.server_manager.set_crop_region(region)
                if not success:
                    logger.warning("Failed to update crop region on server")
                else:
                    logger.info("Updated crop region on server")

        selector.region_confirmed.connect(on_confirmed)
        selector.show()

    def _update_region_display(self):
        """Update region display label."""
        if self.crop_region:
            text = (
                f"Position: ({self.crop_region['x']}, {self.crop_region['y']})  |  "
                f"Size: {self.crop_region['width']}x{self.crop_region['height']}"
            )
            self.region_display.setText(text)
        else:
            self.region_display.setText("No region selected (will use default 50% center)")

    def _on_start_clicked(self):
        """Handle start button click."""
        # Validate inputs
        talk_name = self.talk_name_input.text().strip()
        if not talk_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter a talk title."
            )
            return

        # Calculate default region if not selected
        if not self.crop_region:
            width, height = get_primary_screen_size()
            self.crop_region = calculate_default_region(width, height, 0.5)
            self._update_region_display()

        # Hide form, show countdown
        self.start_button.setEnabled(False)
        self.countdown_widget.setVisible(True)
        self.countdown_widget.start()

        logger.info(f"Starting countdown for talk: {talk_name}")

    def _on_countdown_cancelled(self):
        """Handle countdown cancellation."""
        logger.info("Countdown cancelled, resetting UI")
        self.countdown_widget.setVisible(False)
        self.start_button.setEnabled(True)

    def _start_talk(self):
        """Start the talk (called after countdown finishes)."""
        logger.info("Countdown finished, starting talk...")

        # Hide countdown
        self.countdown_widget.setVisible(False)

        # Show status
        self.status_label.setText("Switching to active mode and starting talk...")
        self.status_group.setVisible(True)

        # Process events to update UI
        QApplication.processEvents()

        try:
            if not self.server_started:
                raise Exception("Server not started. Please restart the application.")

            # Get form data
            talk_name = self.talk_name_input.text().strip()
            presenter = self.presenter_input.text().strip()
            description = self.description_input.toPlainText().strip()
            monitor_id = self.monitor_combo.currentData()
            tolerance = self.tolerance_slider.value() / 100.0  # Convert to 0.0-1.0

            # Start talk (switches from IDLE to ACTIVE mode)
            logger.info(f"Starting talk: {talk_name}")
            self.session_id = self.server_manager.start_talk(
                name=talk_name,
                presenter_name=presenter,
                description=description,
                monitor_id=monitor_id,
                dedup_tolerance=tolerance
            )

            if not self.session_id:
                raise Exception("Failed to start talk")

            # Mark as active
            self.is_active = True

            # Update UI
            self.status_label.setText(f"✅ Talk active: {talk_name}\n\nCapturing slides...")
            self.stop_button.setVisible(True)

            # Start status polling
            self.status_timer.start(5000)  # Poll every 5 seconds

            logger.info(f"Talk started successfully: {self.session_id}")

        except Exception as e:
            logger.error(f"Failed to start talk: {e}")
            QMessageBox.critical(
                self,
                "Failed to Start",
                f"Could not start talk:\n{str(e)}\n\nPlease try again."
            )

            # Reset UI
            self.status_group.setVisible(False)
            self.start_button.setEnabled(True)

    def _poll_status(self):
        """Poll server for live statistics."""
        if not self.is_active:
            return

        try:
            status = self.server_manager.get_status()

            if status:
                active = status.get('active', False)
                talk_name = status.get('talk_name', 'Unknown')

                # Get slides count from stats (if available)
                stats = status.get('stats', {})
                if stats and 'deduplication' in stats:
                    slides_count = stats['deduplication'].get('unique_slides', 0)
                else:
                    slides_count = 0

                logger.debug(f"Status poll: active={active}, talk_name={talk_name}, slides={slides_count}")

                if active:
                    self.status_label.setText(
                        f"✅ Talk active: {talk_name}\n\n"
                        f"Slides captured: {slides_count}"
                    )
                else:
                    # Talk was stopped externally
                    logger.warning(f"Talk appears inactive (active={active}), triggering external stop")
                    self._on_talk_stopped_externally()

        except Exception as e:
            logger.warning(f"Failed to poll status: {e}", exc_info=True)

    def _stop_talk(self):
        """Stop the current talk."""
        if not self.is_active:
            return

        reply = QMessageBox.question(
            self,
            "Stop Talk",
            "Are you sure you want to stop the talk?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            logger.info("Stopping talk...")

            try:
                success = self.server_manager.stop_talk()

                if success:
                    QMessageBox.information(
                        self,
                        "Talk Stopped",
                        "Talk has been stopped successfully.\n\n"
                        "Your slides have been saved and are available in the cloud viewer.\n\n"
                        "You can start a new talk or close this window."
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Stop Failed",
                        "Could not stop talk. The talk may have already ended."
                    )

            except Exception as e:
                logger.error(f"Failed to stop talk: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to stop talk:\n{str(e)}"
                )

            finally:
                # Cleanup but keep server running (switches back to IDLE mode)
                self._cleanup(stop_server=False)
                self.talk_stopped.emit()

                # Reset UI to allow starting another talk
                self.status_group.setVisible(False)
                self.stop_button.setVisible(False)
                self.start_button.setEnabled(True)

    def _on_talk_stopped_externally(self):
        """Handle talk being stopped externally."""
        logger.info("Talk was stopped externally")
        self._cleanup(stop_server=False)

        QMessageBox.information(
            self,
            "Talk Ended",
            "The talk has ended.\n\nYour slides are available in the cloud viewer.\n\n"
            "You can start a new talk or close this window."
        )

        self.talk_stopped.emit()

        # Reset UI to allow starting another talk
        self.status_group.setVisible(False)
        self.stop_button.setVisible(False)
        self.start_button.setEnabled(True)

    def _cleanup(self, stop_server: bool = True):
        """Cleanup resources.

        Args:
            stop_server: If True, stop the server. If False, just reset state.
        """
        logger.info("Cleaning up resources...")

        # Stop polling
        self.status_timer.stop()

        # Stop server only if requested
        if stop_server:
            self.server_manager.cleanup()
            self.server_started = False

        # Reset state
        self.is_active = False
        self.session_id = None

    def closeEvent(self, event):
        """Handle window close event."""
        if self.is_active:
            reply = QMessageBox.question(
                self,
                "Talk Active",
                "A talk is currently active. Stop the talk and exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Stop talk first
                if self.server_started:
                    try:
                        self.server_manager.stop_talk()
                    except:
                        pass

                # Cleanup and stop server
                self._cleanup(stop_server=True)
                event.accept()
            else:
                event.ignore()
        else:
            # No active talk, just cleanup and stop server
            self._cleanup(stop_server=True)
            event.accept()
