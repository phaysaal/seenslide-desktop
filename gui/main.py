#!/usr/bin/env python3
"""SeenSlide GUI Application - Main Entry Point."""

import sys
import logging
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

from gui.windows.mode_selector import ModeSelector
from gui.windows.direct_talk_window import DirectTalkWindow
from gui.windows.conference_launcher import ConferenceLauncher
from gui.widgets.region_selector import RegionSelector
from gui.utils.screenshot_util import capture_screenshot, get_primary_screen_size
from gui.utils.region_utils import calculate_default_region
from gui.utils.portal_session import PortalSessionManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SeenSlideApp:
    """Main application controller."""

    def __init__(self):
        """Initialize application."""
        # Create Qt application
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("SeenSlide")
        self.app.setOrganizationName("SeenSlide")

        # Windows
        self.mode_selector: Optional[ModeSelector] = None
        self.direct_talk_window: Optional[DirectTalkWindow] = None
        self.conference_launcher: Optional[ConferenceLauncher] = None

        # Selected crop region (None = use default)
        self.crop_region: Optional[dict] = None

        logger.info("SeenSlide application initialized")

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code
        """
        # Request screen capture permission first
        logger.info("Requesting screen capture permission...")
        if not PortalSessionManager.request_permission():
            logger.error("Screen capture permission denied, exiting")
            return 1

        # Show mode selector
        self.show_mode_selector()

        # Run event loop
        return self.app.exec_()

    def show_mode_selector(self):
        """Show mode selector window."""
        logger.info("Showing mode selector")

        self.mode_selector = ModeSelector()
        self.mode_selector.direct_talk_selected.connect(self._on_direct_talk_selected)
        self.mode_selector.conference_mode_selected.connect(self._on_conference_mode_selected)
        self.mode_selector.show()

    def _on_direct_talk_selected(self):
        """Handle Direct Talk mode selection."""
        logger.info("User selected Direct Talk mode")

        # Close mode selector
        if self.mode_selector:
            self.mode_selector.close()

        # Show Direct Talk window
        self.direct_talk_window = DirectTalkWindow()
        self.direct_talk_window.talk_stopped.connect(self._on_talk_stopped)
        self.direct_talk_window.close_requested.connect(self._on_direct_talk_closed)
        self.direct_talk_window.show()

    def _on_conference_mode_selected(self):
        """Handle Conference Mode selection."""
        logger.info("User selected Conference Mode")

        # Ask if user wants to select a custom region
        reply = QMessageBox.question(
            self.mode_selector,
            "Capture Region",
            "Would you like to select a custom capture region?\n\n"
            "This region will be used for slide change detection.\n"
            "(Full screen is captured, only this region is compared)\n\n"
            "Click 'Yes' to select a region, or 'No' to use default (50% center).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Show region selector
            self._show_region_selector_for_conference()
        else:
            # Use default region
            width, height = get_primary_screen_size()
            self.crop_region = calculate_default_region(width, height, 0.5)
            logger.info(f"Using default crop region: {self.crop_region}")
            self._launch_conference_mode()

    def _show_region_selector_for_conference(self):
        """Show region selector for Conference Mode."""
        logger.info("Showing region selector for Conference Mode")

        # Verify we have permission
        if not PortalSessionManager.has_permission():
            logger.error("No screen capture permission")
            QMessageBox.critical(
                self.mode_selector,
                "Permission Required",
                "Screen capture permission is required for region selection.\n\n"
                "Please restart the application and grant permission."
            )
            return

        # Capture screenshot
        screenshot = capture_screenshot(monitor_id=1)

        if screenshot is None:
            QMessageBox.warning(
                self.mode_selector,
                "Screenshot Failed",
                "Could not capture screenshot. Using default region."
            )
            # Fall back to default
            width, height = get_primary_screen_size()
            self.crop_region = calculate_default_region(width, height, 0.5)
            self._launch_conference_mode()
            return

        # Calculate default region
        width, height = screenshot.width, screenshot.height
        default_region = calculate_default_region(width, height, 0.5)

        # Show region selector
        selector = RegionSelector(
            screenshot=screenshot,
            default_region=default_region,
            parent=self.mode_selector
        )

        def on_confirmed(region):
            self.crop_region = region
            logger.info(f"User selected crop region: {region}")
            self._launch_conference_mode()

        def on_cancelled():
            logger.info("Region selection cancelled, using default")
            self.crop_region = default_region
            self._launch_conference_mode()

        selector.region_confirmed.connect(on_confirmed)
        selector.selection_cancelled.connect(on_cancelled)
        selector.show()

    def _launch_conference_mode(self):
        """Launch Conference Mode with selected region."""
        logger.info("Launching Conference Mode")

        # Close mode selector
        if self.mode_selector:
            self.mode_selector.close()

        # Launch conference mode
        self.conference_launcher = ConferenceLauncher(crop_region=self.crop_region)
        self.conference_launcher.close_requested.connect(self._on_conference_closed)
        self.conference_launcher.show()

    def _on_talk_stopped(self):
        """Handle talk stopped event."""
        logger.info("Talk stopped")

    def _on_direct_talk_closed(self):
        """Handle Direct Talk window closed."""
        logger.info("Direct Talk window closed")

        # Show mode selector again
        self.show_mode_selector()

    def _on_conference_closed(self):
        """Handle Conference Launcher closed."""
        logger.info("Conference Launcher closed")

        # Show mode selector again
        self.show_mode_selector()


def main():
    """Main entry point."""
    try:
        app = SeenSlideApp()
        exit_code = app.run()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
