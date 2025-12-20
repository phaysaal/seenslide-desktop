"""Interface for screen capture providers."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from core.models.slide import RawCapture


class ICaptureProvider(ABC):
    """Interface for screen capture providers.

    This abstract base class defines the contract that all capture providers
    must implement. Providers can use different backends (mss, scrot, etc.)
    to capture screenshots.
    """

    @abstractmethod
    def initialize(self, config: dict) -> bool:
        """Initialize the capture provider with configuration.

        Args:
            config: Dictionary containing provider-specific configuration

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def list_monitors(self) -> List[Dict]:
        """List available monitors/screens.

        Returns:
            List of dicts with monitor information:
            [{"id": 1, "x": 0, "y": 0, "width": 1920, "height": 1080}]
        """
        pass

    @abstractmethod
    def capture(self, monitor_id: Optional[int] = None) -> RawCapture:
        """Capture a screenshot.

        Args:
            monitor_id: Monitor to capture (None = primary monitor)

        Returns:
            RawCapture object containing the captured image and metadata

        Raises:
            CaptureError: If capture fails
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources used by the capture provider."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'mss', 'scrot')."""
        pass

    @property
    @abstractmethod
    def supported_platforms(self) -> List[str]:
        """List of supported platforms.

        Returns:
            List of platform names: ["linux", "darwin", "win32"]
        """
        pass


class CaptureError(Exception):
    """Exception raised when screen capture fails."""
    pass
