"""Direct Talk Mode window."""

from typing import Optional, Dict
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QSlider, QComboBox, QGroupBox,
    QMessageBox, QApplication, QProgressDialog, QDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont
import logging

from gui.widgets.countdown_widget import CountdownWidget
from gui.widgets.region_selector import RegionSelector
from gui.utils.screenshot_util import capture_screenshot, get_primary_screen_size, get_monitor_count
from gui.utils.region_utils import calculate_default_region
from gui.utils.portal_session import PortalSessionManager
from gui.dialogs.first_collection_dialog import FirstCollectionDialog

# Import orchestrator directly
from seenslide.orchestrator import SeenSlideOrchestrator, CaptureMode

# Import collection management
from core.session.collection_registry import CollectionRegistry, Collection
from core.session.credential_manager import CredentialManager

logger = logging.getLogger(__name__)


class OrchestratorStartWorker(QThread):
    """Worker thread to start orchestrator without blocking GUI."""

    # Signals
    success = pyqtSignal(object, str, str)  # orchestrator, cloud_collection_id, cloud_viewer_url
    error = pyqtSignal(str)  # error message

    def __init__(
        self,
        monitor_id: int,
        crop_region: dict,
        collection: Optional[Collection] = None,
        username: Optional[str] = None,
        password_hash: Optional[str] = None
    ):
        """Initialize worker.

        Args:
            monitor_id: Monitor to capture
            crop_region: Crop region for deduplication
            collection: Existing collection to use (None = create new)
            username: Username for new collection creation
            password_hash: Password hash for new collection
        """
        super().__init__()
        self.monitor_id = monitor_id
        self.crop_region = crop_region
        self.collection = collection
        self.username = username
        self.password_hash = password_hash

    def run(self):
        """Start orchestrator in background thread."""
        try:
            # Find config file
            config_paths = [
                Path.home() / ".config" / "seenslide" / "config.yaml",
                Path(__file__).parent.parent.parent / "config" / "config.yaml",
            ]

            config_path = None
            for path in config_paths:
                if path.exists():
                    config_path = path
                    break

            # Load config file to get cloud settings
            import yaml
            loaded_config = {}
            if config_path:
                with open(config_path, 'r') as f:
                    loaded_config = yaml.safe_load(f) or {}

            # Create orchestrator with config path (it will load config internally)
            orchestrator = SeenSlideOrchestrator(config_path=str(config_path) if config_path else None)

            # Inject cloud settings into orchestrator's config
            if 'cloud' not in orchestrator.config:
                orchestrator.config['cloud'] = {}

            # Copy cloud settings from loaded config first
            cloud_config = loaded_config.get('cloud', {})
            orchestrator.config['cloud'].update(cloud_config)

            # If collection exists, use its cloud ID
            if self.collection:
                # Set existing cloud session ID to reuse
                orchestrator.config['cloud']['existing_session_id'] = self.collection.cloud_collection_id
                logger.info(f"Reusing existing collection: {self.collection.cloud_collection_id}")
            else:
                # Create new collection with username/password
                if self.username:
                    orchestrator.config['cloud']['admin_username'] = self.username
                    orchestrator.config['cloud']['admin_password_hash'] = self.password_hash
                    logger.info(f"Creating new collection for user: {self.username}")

            # Start in IDLE mode (triggers screen permission)
            session_name = self.collection.name if self.collection else "My Presentations 2026"
            success = orchestrator.start_session(
                session_name=f"{session_name} - Idle",
                description="Waiting for talk to start",
                presenter_name="",
                monitor_id=self.monitor_id,
                mode=CaptureMode.IDLE,
                crop_region=self.crop_region
            )

            if not success:
                self.error.emit("Failed to start idle capture")
                return

            logger.info("✅ Orchestrator started in IDLE mode")

            # Get cloud collection info
            cloud_collection_id = None
            cloud_viewer_url = None
            if orchestrator.storage_manager._cloud.enabled:
                cloud_collection_id = orchestrator.storage_manager._cloud.cloud_session_id
                api_url = orchestrator.storage_manager._cloud.api_url
                cloud_viewer_url = f"{api_url}/{cloud_collection_id}"

            self.success.emit(orchestrator, cloud_collection_id or "", cloud_viewer_url or "")

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}", exc_info=True)
            self.error.emit(str(e))


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

        # Collection management
        self.collection_registry = CollectionRegistry()
        self.credential_manager = CredentialManager()
        self.current_collection: Optional[Collection] = None

        # Orchestrator (run directly, no admin server)
        self.orchestrator: Optional[SeenSlideOrchestrator] = None

        # Selected region (default to 50% center)
        width, height = get_primary_screen_size()
        self.crop_region = calculate_default_region(width, height, 0.5)

        # Talk session
        self.session_id: Optional[str] = None
        self.talk_name: Optional[str] = None
        self.presenter_name: Optional[str] = None
        self.cloud_collection_id: Optional[str] = None
        self.cloud_viewer_url: Optional[str] = None
        self.is_active = False

        # Status polling timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_status)

        # Setup UI
        self._setup_ui()

        # Check for collections and start orchestrator
        QTimer.singleShot(500, self._initialize_collection)

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
        #region_info = self._create_region_info()
        #main_layout.addWidget(region_info)

        # Cloud session display (shown after orchestrator starts)
        self.cloud_session_group = self._create_cloud_session_group()
        self.cloud_session_group.setVisible(False)
        main_layout.addWidget(self.cloud_session_group)

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

    def _create_cloud_session_group(self) -> QGroupBox:
        """Create cloud collection info display.

        Returns:
            QGroupBox with cloud collection information
        """
        group = QGroupBox("Cloud Collection", self)
        layout = QVBoxLayout()

        # Session ID display
        self.cloud_session_display = QLabel("Initializing...", self)
        self.cloud_session_display.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                padding: 15px;
                border: 2px solid #2196F3;
                border-radius: 5px;
                color: #1565C0;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.cloud_session_display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.cloud_session_display)

        # Help text
        help_label = QLabel(
            "Share this collection ID with viewers to access your talks online.",
            self
        )
        help_label.setStyleSheet("color: #666; font-size: 11px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

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

    def _initialize_collection(self):
        """Initialize collection (check for existing or create first collection)."""
        logger.info("Initializing collection...")

        # Check if collections exist
        if not self.collection_registry.has_collections():
            logger.info("No collections found, showing first collection dialog")

            # Show first collection dialog
            dialog = FirstCollectionDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                collection_name, username, password_hash, has_password = dialog.get_collection_info()

                # Store for orchestrator creation
                self.new_collection_name = collection_name
                self.new_collection_username = username
                self.new_collection_password_hash = password_hash
                self.new_collection_has_password = has_password

                logger.info(f"First collection will be created: {collection_name} ({username})")

                # Start orchestrator (will create collection)
                self._start_idle_orchestrator()
            else:
                # User cancelled
                logger.info("User cancelled first collection creation")
                QMessageBox.information(
                    self,
                    "Collection Required",
                    "A collection is required to use SeenSlide.\n\n"
                    "The application will now close."
                )
                self.close_requested.emit()
        else:
            # Load current collection
            self.current_collection = self.collection_registry.get_current_collection()

            if self.current_collection:
                logger.info(f"Loaded current collection: {self.current_collection.name} "
                           f"({self.current_collection.cloud_collection_id})")

                # Start orchestrator with existing collection
                self._start_idle_orchestrator()
            else:
                # No current collection (shouldn't happen)
                logger.error("Collections exist but no current collection set")
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to load current collection.\n\n"
                    "Please restart the application."
                )
                self.close_requested.emit()

    def _start_idle_orchestrator(self):
        """Start orchestrator in IDLE mode (no admin server needed)."""
        logger.info("Starting orchestrator in IDLE mode for Direct Talk...")

        # Show progress dialog (non-modal so it doesn't block)
        self.progress_dialog = QProgressDialog(
            "Starting screen capture...\n\n"
            "Please grant screen sharing permission when prompted.\n"
            "This may take a moment...",
            None,  # No cancel button
            0, 0,  # Indeterminate progress
            self
        )
        self.progress_dialog.setWindowTitle("Initializing")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.show()

        # Start orchestrator in background thread
        monitor_id = self.monitor_combo.currentData()

        # Pass collection or new collection info
        if self.current_collection:
            # Existing collection
            self.start_worker = OrchestratorStartWorker(
                monitor_id,
                self.crop_region,
                collection=self.current_collection
            )
        else:
            # New collection (first time)
            self.start_worker = OrchestratorStartWorker(
                monitor_id,
                self.crop_region,
                username=self.new_collection_username,
                password_hash=self.new_collection_password_hash
            )

        self.start_worker.success.connect(self._on_orchestrator_started)
        self.start_worker.error.connect(self._on_orchestrator_error)
        self.start_worker.start()

    def _on_orchestrator_started(self, orchestrator, cloud_collection_id: str, cloud_viewer_url: str):
        """Handle orchestrator startup success."""
        logger.info("✅ Orchestrator started successfully")

        # Close progress dialog
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            del self.progress_dialog

        # Store orchestrator and cloud info
        self.orchestrator = orchestrator
        self.cloud_collection_id = cloud_collection_id if cloud_collection_id else None
        self.cloud_viewer_url = cloud_viewer_url if cloud_viewer_url else None

        # If this was a new collection, save it to registry
        if not self.current_collection and cloud_collection_id:
            logger.info("Saving new collection to registry...")

            # Add to collection registry
            self.current_collection = self.collection_registry.add_collection(
                cloud_collection_id=cloud_collection_id,
                name=self.new_collection_name,
                owner_username=self.new_collection_username,
                is_owner=True,
                access_level="owner",
                has_password=self.new_collection_has_password
            )

            # Store password hash if provided
            if self.new_collection_password_hash:
                self.credential_manager.store_password_hash(
                    cloud_collection_id,
                    self.new_collection_password_hash
                )

            logger.info(f"✅ Collection created and saved: {self.current_collection.collection_id}")

        if self.cloud_collection_id:
            logger.info(f"Cloud collection: {self.cloud_collection_id}")
            logger.info(f"Cloud viewer: {self.cloud_viewer_url}")

            # Show and update cloud session display
            self.cloud_session_group.setVisible(True)
            collection_name = self.current_collection.name if self.current_collection else "Collection"
            session_text = f"📚 {collection_name}\n"
            session_text += f"🌐 ID: {self.cloud_collection_id}\n"
            if self.cloud_viewer_url:
                session_text += f"📺 {self.cloud_viewer_url}"
            self.cloud_session_display.setText(session_text)
        else:
            # Cloud disabled
            self.cloud_session_group.setVisible(False)

        # Update region display
        #self._update_region_display()

        # Enable start button
        self.start_button.setEnabled(True)

    def _on_orchestrator_error(self, error_msg: str):
        """Handle orchestrator startup error."""
        logger.error(f"Orchestrator startup failed: {error_msg}")

        # Close progress dialog
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            del self.progress_dialog

        QMessageBox.critical(
            self,
            "Startup Failed",
            f"Could not start screen capture:\n{error_msg}\n\n"
            "This is likely a screen capture permission issue.\n"
            "Please grant permissions when prompted and try again."
        )
        self.close_requested.emit()

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
            if not self.orchestrator:
                raise Exception("Orchestrator not started. Please restart the application.")

            # Get form data
            talk_name = self.talk_name_input.text().strip()
            presenter = self.presenter_input.text().strip()
            description = self.description_input.toPlainText().strip()
            tolerance = self.tolerance_slider.value() / 100.0  # Convert to 0.0-1.0

            # Create new session for this talk
            from core.models.session import Session
            new_session = Session(
                user_id="direct-talk-user",
                cloud_session_id=self.cloud_session_id,
                name=talk_name,
                description=description,
                presenter_name=presenter or "Unknown",
                capture_interval_seconds=self.orchestrator.config.get("capture", {}).get("interval_seconds", 2.0),
                dedup_strategy=self.orchestrator.config.get("deduplication", {}).get("strategy", "hash")
            )

            logger.info(f"Created session for talk: {talk_name} ({new_session.session_id})")

            # Update orchestrator with new session
            success = self.orchestrator.update_session(new_session)
            if not success:
                raise Exception("Failed to update orchestrator with session")

            # Create talk in cloud session
            if self.orchestrator.storage_manager._cloud.enabled:
                success = self.orchestrator.storage_manager._cloud.create_talk(
                    session_id=new_session.session_id,
                    talk_name=talk_name,
                    presenter_name=presenter or "Unknown",
                    description=description
                )
                if not success:
                    logger.warning("Failed to create talk in cloud, but continuing locally")

            # Update deduplication tolerance
            if 'deduplication' not in self.orchestrator.config:
                self.orchestrator.config['deduplication'] = {}
            self.orchestrator.config['deduplication']['perceptual_threshold'] = tolerance

            # Switch to ACTIVE mode
            success = self.orchestrator.set_capture_mode(CaptureMode.ACTIVE)
            if not success:
                raise Exception("Failed to switch to active mode")

            # Store session info
            self.session_id = new_session.session_id
            self.talk_name = talk_name
            self.presenter_name = presenter
            self.is_active = True

            # Update UI with session info
            self._update_status_display(0)  # Start with 0 slides
            self.stop_button.setVisible(True)

            # Start status polling
            self.status_timer.start(5000)  # Poll every 5 seconds

            logger.info(f"✅ Talk started successfully: {self.session_id}")

        except Exception as e:
            logger.error(f"Failed to start talk: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Failed to Start",
                f"Could not start talk:\n{str(e)}\n\nPlease try again."
            )

            # Reset UI
            self.status_group.setVisible(False)
            self.start_button.setEnabled(True)

    def _update_status_display(self, slides_count: int):
        """Update the status display with collection and talk stats.

        Args:
            slides_count: Number of unique slides captured
        """
        status_text = f"✅ Talk Active\n\n"
        status_text += f"Talk: {self.talk_name}\n"
        status_text += f"Presenter: {self.presenter_name}\n\n"

        # Show cloud collection ID prominently
        if self.cloud_collection_id:
            collection_name = self.current_collection.name if self.current_collection else "Collection"
            status_text += f"📚 Collection: {collection_name}\n"
            status_text += f"🌐 Collection ID: {self.cloud_collection_id}\n"
            if self.cloud_viewer_url:
                status_text += f"📺 Viewer URL: {self.cloud_viewer_url}\n"
            status_text += "\n"

        status_text += f"💾 Local Talk ID: {self.session_id[:8]}...\n\n"
        status_text += f"📊 Slides captured: {slides_count}"

        self.status_label.setText(status_text)

    def _poll_status(self):
        """Poll orchestrator for live statistics."""
        if not self.is_active or not self.orchestrator:
            return

        try:
            # Get stats directly from orchestrator
            stats = self.orchestrator.get_statistics()

            if stats and 'deduplication' in stats:
                slides_count = stats['deduplication'].get('unique_slides', 0)
            else:
                slides_count = 0

            logger.debug(f"Status poll: slides={slides_count}")

            # Update display with current slide count
            self._update_status_display(slides_count)

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
                if self.orchestrator:
                    # Switch back to IDLE mode (keeps session alive for next talk)
                    success = self.orchestrator.set_capture_mode(CaptureMode.IDLE)

                    if success:
                        logger.info("✅ Switched back to IDLE mode")
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
                            "Could not switch back to idle mode."
                        )
                else:
                    QMessageBox.warning(
                        self,
                        "Stop Failed",
                        "Orchestrator not available."
                    )

            except Exception as e:
                logger.error(f"Failed to stop talk: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to stop talk:\n{str(e)}"
                )

            finally:
                # Reset state
                self.is_active = False
                self.status_timer.stop()
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

    def _cleanup(self, stop_orchestrator: bool = True):
        """Cleanup resources.

        Args:
            stop_orchestrator: If True, stop the orchestrator. If False, just reset state.
        """
        logger.info("Cleaning up resources...")

        # Stop polling
        self.status_timer.stop()

        # Stop orchestrator only if requested
        if stop_orchestrator and self.orchestrator:
            try:
                self.orchestrator.stop_session()
                logger.info("Orchestrator stopped")
            except Exception as e:
                logger.error(f"Error stopping orchestrator: {e}")
            self.orchestrator = None

        # Reset state
        self.is_active = False
        self.session_id = None
        self.talk_name = None
        self.presenter_name = None
        # Note: Don't reset cloud_session_id - it persists across talks

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
                if self.orchestrator:
                    try:
                        self.orchestrator.set_capture_mode(CaptureMode.IDLE)
                    except:
                        pass

                # Cleanup and stop orchestrator
                self._cleanup(stop_orchestrator=True)
                self.close_requested.emit()
                event.accept()
            else:
                event.ignore()
        else:
            # No active talk, just cleanup and stop orchestrator
            self._cleanup(stop_orchestrator=True)
            self.close_requested.emit()
            event.accept()
