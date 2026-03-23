"""MSS-based screen capture provider."""

import logging
import time
import threading
from typing import Optional, List, Dict
from PIL import Image
import mss
import mss.tools

from core.interfaces.capture import ICaptureProvider, CaptureError
from core.models.slide import RawCapture

logger = logging.getLogger(__name__)


class MSSCaptureProvider(ICaptureProvider):
    """Screen capture provider using MSS library.

    MSS (Multiple Screen Shots) is a fast, cross-platform screen capture
    library that works on Linux, macOS, and Windows.

    This provider handles MSS's thread-local storage requirements by creating
    a separate MSS instance for each thread that uses it.
    """

    def __init__(self):
        """Initialize the MSS capture provider."""
        self._thread_local = threading.local()
        self._config = {}
        self._initialized = False

    def initialize(self, config: dict) -> bool:
        """Initialize the capture provider with configuration.

        Args:
            config: Dictionary containing provider configuration:
                - monitor_id: int, which monitor to capture (1=primary)
                - quality: int, image quality 0-100 (for JPEG)
                - format: str, image format ('png' or 'jpeg')

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config
            self._initialized = True
            logger.info("MSS capture provider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MSS provider: {e}")
            return False

    def _get_sct(self):
        """Get or create thread-local MSS instance.

        Returns:
            mss.mss instance for the current thread

        Raises:
            CaptureError: If provider not initialized or MSS creation fails
        """
        if not self._initialized:
            raise CaptureError("Provider not initialized")

        # Check if current thread has an MSS instance
        if not hasattr(self._thread_local, 'sct') or self._thread_local.sct is None:
            try:
                self._thread_local.sct = mss.mss()
                logger.debug(f"Created MSS instance for thread {threading.current_thread().name}")
            except Exception as e:
                raise CaptureError(f"Failed to create MSS instance: {e}")

        return self._thread_local.sct

    def list_monitors(self) -> List[Dict]:
        """List available monitors/screens.

        Returns:
            List of dicts with monitor information:
            [{"id": 1, "x": 0, "y": 0, "width": 1920, "height": 1080}, ...]
        """
        monitors = []
        try:
            sct = self._get_sct()
            # Monitor 0 is all monitors combined, skip it
            for i, monitor in enumerate(sct.monitors[1:], start=1):
                monitors.append({
                    "id": i,
                    "x": monitor["left"],
                    "y": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"],
                })
            logger.debug(f"Found {len(monitors)} monitors")
            return monitors
        except Exception as e:
            logger.error(f"Failed to list monitors: {e}")
            raise CaptureError(f"Failed to list monitors: {e}")

    def capture(self, monitor_id: Optional[int] = None) -> RawCapture:
        """Capture a screenshot.

        Args:
            monitor_id: Monitor to capture (None = primary, 1 = first monitor)

        Returns:
            RawCapture object containing the captured image and metadata

        Raises:
            CaptureError: If capture fails
        """
        try:
            sct = self._get_sct()

            # If no monitor specified, use config or default to primary (1)
            if monitor_id is None:
                monitor_id = self._config.get("monitor_id", 1)

            # Validate monitor_id
            if monitor_id < 0 or monitor_id >= len(sct.monitors):
                raise CaptureError(f"Invalid monitor_id: {monitor_id}")

            # Capture the screen
            timestamp = time.time()
            monitor = sct.monitors[monitor_id]
            sct_img = sct.grab(monitor)

            # Convert to PIL Image
            image = Image.frombytes("RGB", sct_img.size, sct_img.rgb)

            # Create RawCapture object
            capture = RawCapture(
                image=image,
                timestamp=timestamp,
                monitor_id=monitor_id,
                width=image.width,
                height=image.height,
                metadata={
                    "provider": self.name,
                    "monitor": monitor,
                    "format": self._config.get("format", "png"),
                }
            )

            logger.debug(
                f"Captured screen: {capture.width}x{capture.height} "
                f"from monitor {monitor_id}"
            )
            return capture

        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            raise CaptureError(f"Failed to capture screen: {e}")

    def cleanup(self) -> None:
        """Clean up resources used by the capture provider."""
        try:
            # Clean up thread-local MSS instance if it exists
            if hasattr(self._thread_local, 'sct') and self._thread_local.sct is not None:
                self._thread_local.sct.close()
                self._thread_local.sct = None
                logger.debug(f"MSS instance cleaned up for thread {threading.current_thread().name}")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        finally:
            self._initialized = False

    @property
    def name(self) -> str:
        """Provider name."""
        return "mss"

    @property
    def supported_platforms(self) -> List[str]:
        """List of supported platforms."""
        return ["linux", "darwin", "win32"]

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
