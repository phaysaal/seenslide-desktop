"""Capture module plugin registration."""

import logging
from core.registry.plugin_registry import PluginRegistry
from modules.capture.providers.mss_provider import MSSCaptureProvider

logger = logging.getLogger(__name__)


def register():
    """Register all capture providers with the plugin registry."""
    registry = PluginRegistry()

    # Register MSS provider
    registry.register_capture_provider("mss", MSSCaptureProvider)

    # Register Portal provider (Wayland support)
    try:
        from modules.capture.providers.portal_provider import PortalCaptureProvider
        registry.register_capture_provider("portal", PortalCaptureProvider)
        logger.debug("Portal provider registered")
    except ImportError as e:
        logger.debug(f"Portal provider not available: {e}")

    logger.debug("Capture providers registered")


# Auto-register on import
register()
