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

        Args:
            parent: Parent widget for dialog

        Returns:
            True if permission granted, False otherwise
        """
        global _portal_session_initialized, _portal_permission_granted

        if _portal_session_initialized and _portal_permission_granted:
            logger.info("Screen capture permission already granted")
            return True

        logger.info("Testing screen capture capability...")

        # Show info dialog explaining what will happen
        QMessageBox.information(
            parent,
            "Screen Capture Setup",
            "SeenSlide needs to capture your screen to detect slide changes.\n\n"
            "Your system may now show a permission dialog.\n"
            "Please grant screen capture permission to continue.\n\n"
            "Click OK to proceed.",
            QMessageBox.Ok
        )

        # Try to initialize screen capture
        # The system will show its own portal dialog if needed
        try:
            from gui.utils.screenshot_util import capture_screenshot

            logger.info("Attempting test screen capture...")
            test_img = capture_screenshot(monitor_id=1)

            if test_img:
                _portal_session_initialized = True
                _portal_permission_granted = True
                logger.info("✅ Screen capture working!")
                return True
            else:
                # Failed to capture
                _portal_session_initialized = True
                _portal_permission_granted = False

                logger.error("Screen capture failed")

                reply = QMessageBox.critical(
                    parent,
                    "Screen Capture Failed",
                    "Failed to capture screen.\n\n"
                    "Possible causes:\n"
                    "• Permission was denied in the system dialog\n"
                    "• You're on Wayland without proper portal setup\n"
                    "• Screen capture is blocked by your system\n\n"
                    "SeenSlide cannot work without screen capture.\n\n"
                    "Would you like to try again?",
                    QMessageBox.Retry | QMessageBox.Close,
                    QMessageBox.Retry
                )

                if reply == QMessageBox.Retry:
                    # Reset and try again
                    _portal_session_initialized = False
                    _portal_permission_granted = False
                    return PortalSessionManager.request_permission(parent)
                else:
                    return False

        except Exception as e:
            logger.error(f"Failed to test screen capture: {e}")

            _portal_session_initialized = True
            _portal_permission_granted = False

            reply = QMessageBox.critical(
                parent,
                "Error",
                f"Failed to initialize screen capture:\n{str(e)}\n\n"
                "This could be a system configuration issue.\n\n"
                "Would you like to try again?",
                QMessageBox.Retry | QMessageBox.Close,
                QMessageBox.Retry
            )

            if reply == QMessageBox.Retry:
                # Reset and try again
                _portal_session_initialized = False
                _portal_permission_granted = False
                return PortalSessionManager.request_permission(parent)
            else:
                return False

    @staticmethod
    def reset():
        """Reset portal session state (for testing)."""
        global _portal_session_initialized, _portal_permission_granted
        _portal_session_initialized = False
        _portal_permission_granted = False
        logger.info("Portal session reset")
