"""Main admin GUI application."""

import logging
import customtkinter as ctk
from typing import Optional

from modules.admin.views.main_window import MainWindow
from core.bus.event_bus import EventBus
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from modules.storage.providers.filesystem_provider import FilesystemStorageProvider

logger = logging.getLogger(__name__)


class AdminApp:
    """Main admin application class."""

    def __init__(self, config: dict = None):
        """Initialize the admin application.

        Args:
            config: Application configuration dictionary
        """
        self.config = config or {}
        self.event_bus = EventBus()
        self.db_provider = SQLiteStorageProvider()
        self.fs_provider = FilesystemStorageProvider()

        # Initialize providers
        storage_config = self.config.get("storage", {})
        if storage_config:
            self.db_provider.initialize(storage_config)
            self.fs_provider.initialize(storage_config)

        # Set appearance mode and color theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Create main window
        self.root = None
        self.main_window = None

    def run(self):
        """Run the admin application."""
        logger.info("Starting SeenSlide Admin GUI")

        # Create main window
        self.root = ctk.CTk()
        self.main_window = MainWindow(
            self.root,
            self.config,
            self.event_bus,
            self.db_provider,
            self.fs_provider
        )

        # Run the application
        self.root.mainloop()

        logger.info("SeenSlide Admin GUI closed")

    def stop(self):
        """Stop the admin application."""
        if self.root:
            self.root.quit()


def main(config_path: Optional[str] = None):
    """Main entry point for admin GUI.

    Args:
        config_path: Path to configuration file (optional)
    """
    from core.config.config_loader import ConfigLoader

    # Load configuration
    config_loader = ConfigLoader()
    if config_path:
        config = config_loader.load_from_file(config_path)
    else:
        config = config_loader.load_defaults()

    # Create and run app
    app = AdminApp(config)
    app.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SeenSlide Admin GUI")
    parser.add_argument("--config", help="Path to configuration file")

    args = parser.parse_args()

    main(config_path=args.config)
