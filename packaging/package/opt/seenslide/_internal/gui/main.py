#!/usr/bin/env python3
"""SeenSlide GUI Application - Main Entry Point."""

import sys
import logging
from pathlib import Path
from typing import Optional


# Add project root to path
# sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

from gui.windows.mode_selector import ModeSelector
from gui.windows.direct_talk_window import DirectTalkWindow
from gui.windows.conference_launcher import ConferenceLauncher
from gui.windows.talk_manager_window import TalkManagerWindow
from gui.widgets.region_selector import RegionSelector
from gui.utils.screenshot_util import capture_screenshot, get_primary_screen_size
from gui.utils.region_utils import calculate_default_region
from gui.utils.portal_session import PortalSessionManager

from seenslide import __version__
from core.updater import UpdateChecker, UpdateDownloader


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
        self.talk_manager: Optional[TalkManagerWindow] = None

        # Selected crop region (None = use default)
        self.crop_region: Optional[dict] = None

        # Auto-update
        self._update_checker: Optional[UpdateChecker] = None
        self._update_downloader: Optional[UpdateDownloader] = None

        logger.info("SeenSlide application initialized")

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code
        """
        # Show mode selector immediately
        # Screen capture permission will be requested when actually needed
        # (when server starts capturing)
        self.show_mode_selector()

        # Run event loop
        return self.app.exec_()

    def show_mode_selector(self):
        """Show mode selector window."""
        logger.info("Showing mode selector")

        self.mode_selector = ModeSelector()
        self.mode_selector.direct_talk_selected.connect(self._on_direct_talk_selected)
        self.mode_selector.conference_mode_selected.connect(self._on_conference_mode_selected)
        self.mode_selector.manage_talks_selected.connect(self._on_manage_talks_selected)

        # Wire update banner signals
        banner = self.mode_selector.update_banner
        banner.download_requested.connect(self._on_download_requested)
        banner.install_requested.connect(self._on_install_requested)
        banner.dismiss_requested.connect(self._on_message_dismissed)

        self.mode_selector.show()

        # Start background update check
        self._start_update_check()

    # ------------------------------------------------------------------
    # Auto-update
    # ------------------------------------------------------------------

    def _start_update_check(self):
        """Launch background thread to check for updates and messages."""
        self._update_checker = UpdateChecker(current_version=__version__)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.message_available.connect(self._on_message_available)
        self._update_checker.start()

    def _on_update_available(self, info: dict):
        """A newer version was found on the server."""
        if self.mode_selector:
            self.mode_selector.update_banner.show_update(info)

    def _on_message_available(self, msg: dict):
        """A broadcast message arrived (shown only if no update banner is visible)."""
        if self.mode_selector:
            banner = self.mode_selector.update_banner
            # Don't replace an update notification with a regular message
            if banner.isHidden():
                banner.show_message(msg)

    def _on_download_requested(self, info: dict):
        """User clicked Download on the update banner."""
        url = info.get("download_url", "")
        if not url:
            logger.warning("No download URL in update info")
            return

        banner = self.mode_selector.update_banner if self.mode_selector else None

        self._update_downloader = UpdateDownloader(
            url=url,
            expected_sha256=info.get("sha256", ""),
        )
        if banner:
            self._update_downloader.progress.connect(banner.set_download_progress)
            self._update_downloader.download_complete.connect(banner.set_download_complete)
            self._update_downloader.download_failed.connect(banner.set_download_failed)
        self._update_downloader.start()

    @staticmethod
    def _on_install_requested(file_path: str):
        """User clicked Install & Restart."""
        from gui.widgets.update_banner import UpdateBanner
        UpdateBanner.launch_installer(file_path)

    @staticmethod
    def _on_message_dismissed(msg_id: str):
        """User dismissed a broadcast message."""
        UpdateChecker.dismiss_message(msg_id)

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

        # Use default region (50% center)
        # User can adjust region later if needed through the admin UI
        width, height = get_primary_screen_size()
        self.crop_region = calculate_default_region(width, height, 0.5)
        logger.info(f"Using default crop region (50% center): {self.crop_region}")

        # Launch conference mode directly
        self._launch_conference_mode()

    def _on_manage_talks_selected(self):
        """Handle Manage Talks selection."""
        logger.info("User selected Manage Talks")

        # Hide mode selector
        if self.mode_selector:
            self.mode_selector.hide()

        # Show talk manager
        self.talk_manager = TalkManagerWindow()
        self.talk_manager.close_requested.connect(self._on_talk_manager_closed)
        self.talk_manager.show()

    def _on_talk_manager_closed(self):
        """Handle talk manager window closed."""
        logger.info("Talk manager closed")

        # Show mode selector again
        self.show_mode_selector()

    def _show_region_selector_for_conference(self):
        """Show region selector for Conference Mode."""
        logger.info("Showing region selector for Conference Mode")

        # Capture screenshot (will trigger portal dialog if needed)
        screenshot = capture_screenshot(monitor_id=1)

        if screenshot is None:
            logger.warning("Failed to capture screenshot for region selection")

            reply = QMessageBox.warning(
                self.mode_selector,
                "Screenshot Failed",
                "Could not capture screenshot for region selection.\n\n"
                "This could be due to:\n"
                "• Screen capture permission denied\n"
                "• X11/Wayland configuration issues\n"
                "• Display server problems\n\n"
                "Would you like to use the default region (50% center) instead?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                # Fall back to default
                width, height = get_primary_screen_size()
                self.crop_region = calculate_default_region(width, height, 0.5)
                self._launch_conference_mode()
            else:
                # User cancelled, go back to mode selector
                logger.info("User cancelled region selection")
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
        self.conference_launcher.quit_application.connect(self._on_quit_application)
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

    def _on_quit_application(self):
        """Handle application quit request."""
        logger.info("Application quit requested")

        # Close all windows
        if self.conference_launcher:
            self.conference_launcher.close()
        if self.direct_talk_window:
            self.direct_talk_window.close()
        if self.mode_selector:
            self.mode_selector.close()

        # Quit the application
        self.app.quit()


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
