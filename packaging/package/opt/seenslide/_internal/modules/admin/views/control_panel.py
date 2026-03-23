"""Control panel for system operations."""

import logging
import customtkinter as ctk

logger = logging.getLogger(__name__)


class ControlPanel:
    """Panel for controlling capture and sessions."""

    def __init__(self, parent, config, event_bus):
        """Initialize the control panel.

        Args:
            parent: Parent widget
            config: Application configuration
            event_bus: Event bus for publishing commands
        """
        self.config = config
        self.event_bus = event_bus
        self.running = False

        # Create frame
        self.frame = ctk.CTkFrame(parent)

        # Create widgets
        self._create_widgets()

        logger.debug("Control panel initialized")

    def _create_widgets(self):
        """Create panel widgets."""
        # Title
        title = ctk.CTkLabel(
            self.frame,
            text="System Control",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(10, 20))

        # Session name input
        name_frame = ctk.CTkFrame(self.frame)
        name_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(name_frame, text="Session Name:").pack(side="left", padx=5)
        self.session_name_entry = ctk.CTkEntry(name_frame, width=200)
        self.session_name_entry.pack(side="left", padx=5)
        self.session_name_entry.insert(0, "Presentation Session")

        # Control buttons
        button_frame = ctk.CTkFrame(self.frame)
        button_frame.pack(pady=10)

        self.start_button = ctk.CTkButton(
            button_frame,
            text="Start Capture",
            command=self._start_capture,
            fg_color="green",
            width=150
        )
        self.start_button.pack(side="left", padx=5)

        self.stop_button = ctk.CTkButton(
            button_frame,
            text="Stop Capture",
            command=self._stop_capture,
            fg_color="red",
            width=150,
            state="disabled"
        )
        self.stop_button.pack(side="left", padx=5)

        # Status label
        self.status_label = ctk.CTkLabel(
            self.frame,
            text="Status: Idle",
            font=ctk.CTkFont(size=14)
        )
        self.status_label.pack(pady=10)

    def _start_capture(self):
        """Start capture session."""
        session_name = self.session_name_entry.get() or "Presentation Session"

        self.running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_label.configure(text=f"Status: Running - {session_name}")

        logger.info(f"Started capture session: {session_name}")

    def _stop_capture(self):
        """Stop capture session."""
        self.running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_label.configure(text="Status: Idle")

        logger.info("Stopped capture session")
