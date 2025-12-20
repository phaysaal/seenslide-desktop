"""Main window for SeenSlide admin GUI."""

import logging
import customtkinter as ctk
from typing import Optional

from modules.admin.views.session_panel import SessionPanel
from modules.admin.views.control_panel import ControlPanel
from modules.admin.views.status_panel import StatusPanel

logger = logging.getLogger(__name__)


class MainWindow:
    """Main window containing all GUI panels."""

    def __init__(self, root, config, event_bus, db_provider, fs_provider):
        """Initialize the main window.

        Args:
            root: CTk root window
            config: Application configuration
            event_bus: Event bus for real-time updates
            db_provider: Database storage provider
            fs_provider: Filesystem storage provider
        """
        self.root = root
        self.config = config
        self.event_bus = event_bus
        self.db_provider = db_provider
        self.fs_provider = fs_provider

        # Configure window
        self.root.title("SeenSlide - Admin Control Panel")
        self.root.geometry("1200x800")

        # Create layout
        self._create_layout()

        logger.info("Main window initialized")

    def _create_layout(self):
        """Create the window layout."""
        # Configure grid
        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=3)

        # Create panels
        self.control_panel = ControlPanel(
            self.root,
            self.config,
            self.event_bus
        )
        self.control_panel.frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.status_panel = StatusPanel(
            self.root,
            self.event_bus
        )
        self.status_panel.frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.session_panel = SessionPanel(
            self.root,
            self.config,
            self.event_bus,
            self.db_provider,
            self.fs_provider
        )
        self.session_panel.frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
