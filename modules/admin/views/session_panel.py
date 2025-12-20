"""Session and slide viewer panel."""

import logging
import customtkinter as ctk
from PIL import Image
from typing import List, Optional

from core.models.slide import ProcessedSlide

logger = logging.getLogger(__name__)


class SessionPanel:
    """Panel for viewing sessions and slides."""

    def __init__(self, parent, config, event_bus, db_provider, fs_provider):
        """Initialize the session panel.

        Args:
            parent: Parent widget
            config: Application configuration
            event_bus: Event bus for receiving updates
            db_provider: Database storage provider
            fs_provider: Filesystem storage provider
        """
        self.config = config
        self.event_bus = event_bus
        self.db_provider = db_provider
        self.fs_provider = fs_provider

        self.current_session_id = None
        self.slides: List[ProcessedSlide] = []

        # Create frame
        self.frame = ctk.CTkFrame(parent)

        # Create widgets
        self._create_widgets()

        logger.debug("Session panel initialized")

    def _create_widgets(self):
        """Create panel widgets."""
        # Title
        title = ctk.CTkLabel(
            self.frame,
            text="Sessions & Slides",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(10, 20))

        # Create horizontal layout
        content_frame = ctk.CTkFrame(self.frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left side - Session list
        left_frame = ctk.CTkFrame(content_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=5)

        ctk.CTkLabel(
            left_frame,
            text="Sessions",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=5)

        self.session_listbox = ctk.CTkTextbox(left_frame, height=200)
        self.session_listbox.pack(fill="both", expand=True, pady=5)
        self.session_listbox.insert("1.0", "No sessions available\n")
        self.session_listbox.configure(state="disabled")

        refresh_button = ctk.CTkButton(
            left_frame,
            text="Refresh Sessions",
            command=self._refresh_sessions
        )
        refresh_button.pack(pady=5)

        # Right side - Slide viewer
        right_frame = ctk.CTkFrame(content_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=5)

        ctk.CTkLabel(
            right_frame,
            text="Slides",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=5)

        self.slide_count_label = ctk.CTkLabel(
            right_frame,
            text="No session selected"
        )
        self.slide_count_label.pack(pady=5)

        # Slide display area
        self.slide_display = ctk.CTkLabel(
            right_frame,
            text="No slide to display",
            width=600,
            height=400
        )
        self.slide_display.pack(pady=10)

    def _refresh_sessions(self):
        """Refresh the list of sessions."""
        # TODO: Implement session listing when available in db_provider
        self.session_listbox.configure(state="normal")
        self.session_listbox.delete("1.0", "end")
        self.session_listbox.insert("1.0", "Session listing not yet implemented\n")
        self.session_listbox.configure(state="disabled")

        logger.info("Refreshed sessions")
