"""Plugin registry for managing pluggable components."""

import logging
from typing import Dict, List, Type, Optional

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Singleton registry for all plugin types.

    The plugin registry maintains a catalog of available implementations
    for each pluggable interface (capture, dedup, storage). Modules can
    register their implementations, and other modules can retrieve them
    by name.

    Example:
        registry = PluginRegistry()
        registry.register_capture_provider("mss", MSSCaptureProvider)
        provider_class = registry.get_capture_provider("mss")
        provider = provider_class()
    """

    _instance = None

    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the plugin registry."""
        if self._initialized:
            return

        self._capture_providers: Dict[str, Type] = {}
        self._dedup_strategies: Dict[str, Type] = {}
        self._storage_providers: Dict[str, Type] = {}
        self._initialized = True

        logger.info("PluginRegistry initialized")

    # Capture provider methods
    def register_capture_provider(self, name: str, provider_class: Type) -> None:
        """Register a capture provider.

        Args:
            name: Unique name for the provider (e.g., "mss", "scrot")
            provider_class: Class implementing ICaptureProvider
        """
        self._capture_providers[name] = provider_class
        logger.info(f"Registered capture provider: {name}")

    def get_capture_provider(self, name: str) -> Optional[Type]:
        """Get a capture provider by name.

        Args:
            name: Name of the provider

        Returns:
            Provider class or None if not found
        """
        return self._capture_providers.get(name)

    def list_capture_providers(self) -> List[str]:
        """List all registered capture providers.

        Returns:
            List of provider names
        """
        return list(self._capture_providers.keys())

    # Deduplication strategy methods
    def register_dedup_strategy(self, name: str, strategy_class: Type) -> None:
        """Register a deduplication strategy.

        Args:
            name: Unique name for the strategy (e.g., "hash", "perceptual")
            strategy_class: Class implementing IDeduplicationStrategy
        """
        self._dedup_strategies[name] = strategy_class
        logger.info(f"Registered dedup strategy: {name}")

    def get_dedup_strategy(self, name: str) -> Optional[Type]:
        """Get a deduplication strategy by name.

        Args:
            name: Name of the strategy

        Returns:
            Strategy class or None if not found
        """
        return self._dedup_strategies.get(name)

    def list_dedup_strategies(self) -> List[str]:
        """List all registered deduplication strategies.

        Returns:
            List of strategy names
        """
        return list(self._dedup_strategies.keys())

    # Storage provider methods
    def register_storage_provider(self, name: str, provider_class: Type) -> None:
        """Register a storage provider.

        Args:
            name: Unique name for the provider (e.g., "filesystem", "sqlite")
            provider_class: Class implementing IStorageProvider
        """
        self._storage_providers[name] = provider_class
        logger.info(f"Registered storage provider: {name}")

    def get_storage_provider(self, name: str) -> Optional[Type]:
        """Get a storage provider by name.

        Args:
            name: Name of the provider

        Returns:
            Provider class or None if not found
        """
        return self._storage_providers.get(name)

    def list_storage_providers(self) -> List[str]:
        """List all registered storage providers.

        Returns:
            List of provider names
        """
        return list(self._storage_providers.keys())

    def clear(self) -> None:
        """Clear all registrations (mainly for testing)."""
        self._capture_providers.clear()
        self._dedup_strategies.clear()
        self._storage_providers.clear()
        logger.debug("Plugin registry cleared")
