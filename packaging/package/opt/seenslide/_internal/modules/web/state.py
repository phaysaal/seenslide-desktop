"""Application state management for web server."""

from typing import Optional, Dict
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from modules.storage.providers.filesystem_provider import FilesystemStorageProvider
from core.bus.event_bus import EventBus


class AppState:
    """Application state container.

    Holds references to storage providers and event bus for
    dependency injection into API endpoints.
    """

    def __init__(
        self,
        db_provider: Optional[SQLiteStorageProvider] = None,
        fs_provider: Optional[FilesystemStorageProvider] = None,
        event_bus: Optional[EventBus] = None,
        config: Optional[Dict] = None
    ):
        """Initialize application state.

        Args:
            db_provider: SQLite storage provider
            fs_provider: Filesystem storage provider
            event_bus: Event bus for real-time updates
            config: Configuration dictionary
        """
        self.db_provider = db_provider or SQLiteStorageProvider()
        self.fs_provider = fs_provider or FilesystemStorageProvider()
        self.event_bus = event_bus or EventBus()
        self.config = config or {}

        # Initialize providers if config provided
        if config:
            self.db_provider.initialize(config)
            self.fs_provider.initialize(config)

    def get_db_provider(self) -> SQLiteStorageProvider:
        """Get database storage provider."""
        return self.db_provider

    def get_fs_provider(self) -> FilesystemStorageProvider:
        """Get filesystem storage provider."""
        return self.fs_provider

    def get_event_bus(self) -> EventBus:
        """Get event bus."""
        return self.event_bus

    def get_config(self) -> Dict:
        """Get configuration."""
        return self.config
