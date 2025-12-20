"""Capture daemon for continuous screen capture."""

import logging
import time
import threading
from typing import Optional

from core.bus.event_bus import EventBus
from core.interfaces.events import Event, EventType
from core.interfaces.capture import ICaptureProvider, CaptureError
from core.models.session import Session

logger = logging.getLogger(__name__)


class CaptureDaemon:
    """Daemon for continuous screen capture.

    The capture daemon runs in a separate thread and captures screens
    at regular intervals, publishing SLIDE_CAPTURED events when successful.
    """

    def __init__(
        self,
        provider: ICaptureProvider,
        session: Session,
        event_bus: Optional[EventBus] = None
    ):
        """Initialize the capture daemon.

        Args:
            provider: Initialized capture provider
            session: Session configuration
            event_bus: Event bus for publishing events (None = create new)
        """
        self._provider = provider
        self._session = session
        self._event_bus = event_bus or EventBus()

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False
        self._stop_event = threading.Event()

        self._capture_count = 0
        self._error_count = 0
        self._last_capture_time = 0.0

        logger.info(
            f"CaptureDaemon initialized for session: {session.session_id}"
        )

    def start(self) -> bool:
        """Start the capture daemon.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning("Capture daemon already running")
            return False

        try:
            # Check if provider needs special initialization (e.g., Portal)
            if hasattr(self._provider, 'start_screencast'):
                logger.info("Starting screencast for portal provider...")
                if not self._provider.start_screencast():
                    logger.error("Failed to start screencast")
                    return False
                logger.info("Screencast started, waiting for frames...")
                # Give stream time to initialize
                time.sleep(1.0)

            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._capture_loop,
                name="CaptureDaemon",
                daemon=True
            )
            self._thread.start()

            # Publish session started event
            self._event_bus.publish(Event(
                type=EventType.SESSION_STARTED,
                data={
                    "session_id": self._session.session_id,
                    "interval_seconds": self._session.capture_interval_seconds,
                },
                source="capture_daemon"
            ))

            logger.info("Capture daemon started")
            return True

        except Exception as e:
            logger.error(f"Failed to start capture daemon: {e}")
            self._running = False
            return False

    def stop(self) -> bool:
        """Stop the capture daemon.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._running:
            logger.warning("Capture daemon not running")
            return False

        try:
            logger.info("Stopping capture daemon...")
            self._running = False
            self._stop_event.set()

            # Wait for thread to finish (with timeout)
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
                if self._thread.is_alive():
                    logger.warning("Capture daemon did not stop gracefully")

            # Stop screencast if provider supports it
            if hasattr(self._provider, 'stop_screencast'):
                logger.info("Stopping screencast...")
                self._provider.stop_screencast()

            # Publish session stopped event
            self._event_bus.publish(Event(
                type=EventType.SESSION_STOPPED,
                data={
                    "session_id": self._session.session_id,
                    "capture_count": self._capture_count,
                    "error_count": self._error_count,
                },
                source="capture_daemon"
            ))

            logger.info(
                f"Capture daemon stopped. "
                f"Captures: {self._capture_count}, Errors: {self._error_count}"
            )
            return True

        except Exception as e:
            logger.error(f"Error stopping capture daemon: {e}")
            return False

    def pause(self) -> None:
        """Pause capture (stops capturing but keeps daemon running)."""
        if not self._running:
            logger.warning("Cannot pause: daemon not running")
            return

        self._paused = True

        # Publish session paused event
        self._event_bus.publish(Event(
            type=EventType.SESSION_PAUSED,
            data={"session_id": self._session.session_id},
            source="capture_daemon"
        ))

        logger.info("Capture daemon paused")

    def resume(self) -> None:
        """Resume capture after pause."""
        if not self._running:
            logger.warning("Cannot resume: daemon not running")
            return

        self._paused = False

        # Publish session started event (resumed)
        self._event_bus.publish(Event(
            type=EventType.SESSION_STARTED,
            data={
                "session_id": self._session.session_id,
                "resumed": True,
            },
            source="capture_daemon"
        ))

        logger.info("Capture daemon resumed")

    def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if running, False otherwise
        """
        return self._running

    def is_paused(self) -> bool:
        """Check if daemon is paused.

        Returns:
            True if paused, False otherwise
        """
        return self._paused

    def get_stats(self) -> dict:
        """Get capture statistics.

        Returns:
            Dictionary containing capture statistics
        """
        return {
            "capture_count": self._capture_count,
            "error_count": self._error_count,
            "last_capture_time": self._last_capture_time,
            "running": self._running,
            "paused": self._paused,
        }

    def _capture_loop(self) -> None:
        """Main capture loop (runs in separate thread)."""
        logger.debug("Capture loop started")

        while self._running:
            try:
                # Check if we should stop
                if self._stop_event.wait(timeout=0.1):
                    break

                # Skip capture if paused
                if self._paused:
                    continue

                # Check if it's time to capture
                current_time = time.time()
                time_since_last = current_time - self._last_capture_time

                if time_since_last < self._session.capture_interval_seconds:
                    # Not time yet, sleep a bit
                    continue

                # Perform capture
                self._perform_capture()

            except Exception as e:
                logger.error(f"Error in capture loop: {e}", exc_info=True)
                self._error_count += 1

                # Publish error event
                self._event_bus.publish(Event(
                    type=EventType.ERROR_OCCURRED,
                    data={
                        "error": str(e),
                        "source": "capture_loop",
                    },
                    source="capture_daemon"
                ))

        logger.debug("Capture loop ended")

    def _perform_capture(self) -> None:
        """Perform a single screen capture."""
        try:
            # Capture screen
            capture = self._provider.capture()
            self._capture_count += 1
            self._last_capture_time = time.time()

            # Publish capture event
            self._event_bus.publish(Event(
                type=EventType.SLIDE_CAPTURED,
                data={
                    "session_id": self._session.session_id,
                    "capture_id": capture.capture_id,
                    "timestamp": capture.timestamp,
                    "width": capture.width,
                    "height": capture.height,
                    "monitor_id": capture.monitor_id,
                    "capture": capture,  # Pass the full capture object
                },
                source="capture_daemon"
            ))

            logger.debug(
                f"Captured slide #{self._capture_count}: {capture.capture_id}"
            )

        except CaptureError as e:
            logger.error(f"Capture failed: {e}")
            self._error_count += 1

            # Publish capture failed event
            self._event_bus.publish(Event(
                type=EventType.CAPTURE_FAILED,
                data={
                    "session_id": self._session.session_id,
                    "error": str(e),
                },
                source="capture_daemon"
            ))


def main():
    """Main entry point for running capture daemon standalone."""
    import sys
    from core.config import load_config
    from core.registry.plugin_registry import PluginRegistry

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        # Load configuration
        config = load_config()

        # Import plugin to register providers
        import modules.capture.plugin

        # Get capture provider
        registry = PluginRegistry()
        provider_name = config["capture"]["provider"]
        provider_class = registry.get_capture_provider(provider_name)

        if not provider_class:
            logger.error(f"Capture provider not found: {provider_name}")
            sys.exit(1)

        # Initialize provider
        provider = provider_class()
        if not provider.initialize(config["capture"].get("config", {})):
            logger.error("Failed to initialize capture provider")
            sys.exit(1)

        # Create session
        session = Session(
            name="Standalone Capture Session",
            capture_interval_seconds=config.get(
                "session", {}
            ).get("capture_interval_seconds", 2.0)
        )

        # Create and start daemon
        daemon = CaptureDaemon(provider, session)
        daemon.start()

        # Run until interrupted
        logger.info("Capture daemon running. Press Ctrl+C to stop.")
        try:
            while daemon.is_running():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")

        # Stop daemon
        daemon.stop()
        provider.cleanup()

        logger.info("Capture daemon terminated")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
