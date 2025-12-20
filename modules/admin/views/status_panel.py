"""Status panel showing system information."""

import logging
import customtkinter as ctk
from core.interfaces.events import EventType

logger = logging.getLogger(__name__)


class StatusPanel:
    """Panel for displaying system status and events."""

    def __init__(self, parent, event_bus):
        """Initialize the status panel.

        Args:
            parent: Parent widget
            event_bus: Event bus for receiving updates
        """
        self.event_bus = event_bus

        # Create frame
        self.frame = ctk.CTkFrame(parent)

        # Create widgets
        self._create_widgets()

        # Subscribe to events
        self._subscribe_to_events()

        logger.debug("Status panel initialized")

    def _create_widgets(self):
        """Create panel widgets."""
        # Title
        title = ctk.CTkLabel(
            self.frame,
            text="System Status",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(10, 20))

        # Event log
        log_label = ctk.CTkLabel(
            self.frame,
            text="Recent Events:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        log_label.pack(pady=5)

        self.event_log = ctk.CTkTextbox(self.frame, height=150)
        self.event_log.pack(fill="both", expand=True, padx=10, pady=10)
        self.event_log.configure(state="disabled")

        self._add_log_entry("System initialized")

    def _subscribe_to_events(self):
        """Subscribe to event bus events."""
        event_types = [
            EventType.SESSION_CREATED,
            EventType.SESSION_STARTED,
            EventType.SESSION_STOPPED,
            EventType.SLIDE_CAPTURED,
            EventType.SLIDE_UNIQUE,
            EventType.SLIDE_STORED,
            EventType.CAPTURE_ERROR,
            EventType.DEDUP_ERROR,
            EventType.STORAGE_ERROR,
        ]

        for event_type in event_types:
            self.event_bus.subscribe(event_type, self._handle_event)

    def _handle_event(self, event):
        """Handle incoming events.

        Args:
            event: Event object
        """
        event_name = event.type.value if hasattr(event.type, 'value') else str(event.type)
        self._add_log_entry(f"{event_name} - {event.source}")

    def _add_log_entry(self, message: str):
        """Add an entry to the event log.

        Args:
            message: Log message
        """
        self.event_log.configure(state="normal")
        self.event_log.insert("end", f"{message}\n")
        self.event_log.see("end")
        self.event_log.configure(state="disabled")
