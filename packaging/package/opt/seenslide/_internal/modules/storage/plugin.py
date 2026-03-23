"""Storage module plugin registration."""

import logging
from core.registry.plugin_registry import PluginRegistry
from modules.storage.providers.filesystem_provider import FilesystemStorageProvider
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider

logger = logging.getLogger(__name__)


def register():
    """Register all storage providers with the plugin registry."""
    registry = PluginRegistry()

    # Register storage providers
    registry.register_storage_provider("filesystem", FilesystemStorageProvider)
    registry.register_storage_provider("sqlite", SQLiteStorageProvider)

    logger.debug("Storage providers registered")


# Auto-register on import
register()
