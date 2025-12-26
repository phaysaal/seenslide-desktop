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

        logger.info("Requesting screen capture permission...")

        # Show permission dialog
        reply = QMessageBox.question(
            parent,
            "Screen Capture Permission",
            "SeenSlide needs permission to capture your screen.\n\n"
            "This permission is required for:\n"
            "• Selecting capture regions\n"
            "• Capturing slide changes during presentations\n\n"
            "Your screen will only be captured when you start a talk.\n\n"
            "Grant screen capture permission?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # Try to initialize screen capture
            try:
                # Test if we can capture screen
                from gui.utils.screenshot_util import capture_screenshot

                test_img = capture_screenshot(monitor_id=1)

                if test_img:
                    _portal_session_initialized = True
                    _portal_permission_granted = True
                    logger.info("✅ Screen capture permission granted")

                    QMessageBox.information(
                        parent,
                        "Permission Granted",
                        "Screen capture permission granted successfully!\n\n"
                        "You can now proceed with region selection and capturing."
                    )
                    return True
                else:
                    # Failed to capture
                    _portal_session_initialized = True
                    _portal_permission_granted = False

                    QMessageBox.critical(
                        parent,
                        "Permission Denied",
                        "Failed to capture screen. Please check:\n\n"
                        "• System permissions are granted\n"
                        "• You're using X11 or have portal access\n"
                        "• No other application is blocking screen capture\n\n"
                        "SeenSlide cannot function without screen capture permission."
                    )
                    return False

            except Exception as e:
                logger.error(f"Failed to test screen capture: {e}")

                _portal_session_initialized = True
                _portal_permission_granted = False

                QMessageBox.critical(
                    parent,
                    "Error",
                    f"Failed to initialize screen capture:\n{str(e)}\n\n"
                    "Please check your system configuration."
                )
                return False
        else:
            # User declined
            _portal_session_initialized = True
            _portal_permission_granted = False

            logger.warning("User declined screen capture permission")

            QMessageBox.warning(
                parent,
                "Permission Required",
                "Screen capture permission is required for SeenSlide to function.\n\n"
                "Without this permission, you cannot:\n"
                "• Select capture regions\n"
                "• Capture slides during presentations\n\n"
                "The application will now exit."
            )
            return False

    @staticmethod
    def reset():
        """Reset portal session state (for testing)."""
        global _portal_session_initialized, _portal_permission_granted
        _portal_session_initialized = False
        _portal_permission_granted = False
        logger.info("Portal session reset")
