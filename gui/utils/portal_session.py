"""Portal session manager for screen capture permissions."""

import logging
from typing import Optional
from PyQt5.QtWidgets import QMessageBox, QApplication

logger = logging.getLogger(__name__)

# Global portal session state
_portal_session_initialized = False
_portal_permission_granted = False


class PortalSessionManager:
    """Manages screen capture permissions via portal or system."""

    @staticmethod
    def is_initialized() -> bool:
        """Check if portal session is initialized.

        Returns:
            True if initialized, False otherwise
        """
        global _portal_session_initialized
        return _portal_session_initialized

    @staticmethod
    def has_permission() -> bool:
        """Check if screen capture permission is granted.

        Returns:
            True if permission granted, False otherwise
        """
        global _portal_permission_granted
        return _portal_permission_granted

    @staticmethod
    def request_permission(parent=None) -> bool:
        """Request screen capture permission from user.

        This is a simplified version that just marks permission as granted
        and lets the actual capture operations handle any errors.

        Args:
            parent: Parent widget for dialog

        Returns:
            Always True (actual permission handled by capture operations)
        """
        global _portal_session_initialized, _portal_permission_granted

        if _portal_session_initialized and _portal_permission_granted:
            logger.info("Screen capture already initialized")
            return True

        # Just mark as initialized - let actual capture operations handle permissions
        _portal_session_initialized = True
        _portal_permission_granted = True
        logger.info("Screen capture initialized (will be tested on first use)")

        return True

    @staticmethod
    def reset():
        """Reset portal session state (for testing)."""
        global _portal_session_initialized, _portal_permission_granted
        _portal_session_initialized = False
        _portal_permission_granted = False
        logger.info("Portal session reset")
