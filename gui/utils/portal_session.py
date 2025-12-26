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

        This triggers the REAL system permission dialog immediately.

        Args:
            parent: Parent widget for dialog

        Returns:
            True if permission granted, False otherwise
        """
        global _portal_session_initialized, _portal_permission_granted

        if _portal_session_initialized:
            logger.info("Screen capture already initialized")
            return _portal_permission_granted

        logger.info("Triggering system screen capture permission dialog...")

        # Import here to trigger portal dialog
        try:
            from gui.utils.screenshot_util import get_screen_info

            # This will trigger the system's REAL permission dialog
            # If on Wayland with portal, user will see the system dialog
            screens = get_screen_info()

            if screens and len(screens) > 0:
                _portal_session_initialized = True
                _portal_permission_granted = True
                logger.info("✅ Screen capture permission granted")
                return True
            else:
                _portal_session_initialized = True
                _portal_permission_granted = False
                logger.error("Failed to get screen info")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize screen capture: {e}")
            _portal_session_initialized = True
            _portal_permission_granted = False
            return False

    @staticmethod
    def reset():
        """Reset portal session state (for testing)."""
        global _portal_session_initialized, _portal_permission_granted
        _portal_session_initialized = False
        _portal_permission_granted = False
        logger.info("Portal session reset")
