"""Main orchestrator for SeenSlide system."""

import logging
from typing import Optional
import time

from core.bus.event_bus import EventBus
from core.models.session import Session
from core.models.capture_mode import CaptureMode
from core.config.config_loader import ConfigLoader
from core.registry.plugin_registry import PluginRegistry
from modules.capture.daemon import CaptureDaemon
from modules.dedup.engine import DeduplicationEngine
from modules.dedup.strategies.hash_strategy import HashDeduplicationStrategy
from modules.dedup.strategies.perceptual_strategy import PerceptualDeduplicationStrategy
from modules.dedup.strategies.hybrid_strategy import HybridDeduplicationStrategy
from modules.storage.manager import StorageManager

# Import plugins to register providers
import modules.capture.plugin

logger = logging.getLogger(__name__)


class SeenSlideOrchestrator:
    """Main orchestrator coordinating all SeenSlide modules.

    The orchestrator manages the lifecycle of all components and
    coordinates their interactions through the event bus.
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the orchestrator.

        Args:
            config_path: Path to configuration file (optional)
        """
        # Load configuration
        config_loader = ConfigLoader()
        if config_path:
            self.config = config_loader.load_from_file(config_path)
        else:
            self.config = config_loader.load_defaults()

        # Create event bus
        self.event_bus = EventBus()

        # Initialize components
        self.session: Optional[Session] = None
        self.capture_daemon: Optional[CaptureDaemon] = None
        self.dedup_engine: Optional[DeduplicationEngine] = None
        self.storage_manager: Optional[StorageManager] = None

        self._running = False

        logger.info("SeenSlide orchestrator initialized")

    def start_session(
        self,
        session_name: str,
        description: str = "",
        presenter_name: str = "",
        monitor_id: int = 1,
        mode: CaptureMode = CaptureMode.ACTIVE
    ) -> bool:
        """Start a new capture session.

        Args:
            session_name: Name of the session
            description: Session description
            presenter_name: Name of presenter
            monitor_id: Monitor to capture from
            mode: Capture mode (IDLE or ACTIVE)

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning("Session already running")
            return False

        try:
            # Create session
            capture_config = self.config.get("capture", {})
            dedup_config = self.config.get("deduplication", {})

            self.session = Session(
                name=session_name,
                description=description,
                presenter_name=presenter_name,
                capture_interval_seconds=capture_config.get("interval_seconds", 2.0),
                dedup_strategy=dedup_config.get("strategy", "hash")
            )

            # Initialize capture daemon
            registry = PluginRegistry()
            provider_name = capture_config.get("provider", "mss")
            provider_class = registry.get_capture_provider(provider_name)

            if not provider_class:
                logger.error(f"Capture provider '{provider_name}' not found")
                return False

            capture_provider = provider_class()
            provider_config = capture_config.get("config", {})
            if not capture_provider.initialize(provider_config):
                logger.error(f"Failed to initialize capture provider '{provider_name}'")
                return False

            self.capture_daemon = CaptureDaemon(
                provider=capture_provider,
                session=self.session,
                event_bus=self.event_bus,
                mode=mode
            )

            # Initialize deduplication engine
            strategy = self._create_dedup_strategy(dedup_config)
            self.dedup_engine = DeduplicationEngine(
                strategy=strategy,
                session=self.session,
                event_bus=self.event_bus
            )

            # Initialize storage manager
            # Pass full config so storage manager can access both storage and cloud sections
            self.storage_manager = StorageManager(
                session=self.session,
                config=self.config,  # Pass entire config, not just storage section
                event_bus=self.event_bus
            )

            # Start all components
            if not self.capture_daemon.start():
                raise Exception("Failed to start capture daemon")

            if not self.dedup_engine.start():
                raise Exception("Failed to start deduplication engine")

            if not self.storage_manager.start():
                raise Exception("Failed to start storage manager")

            self._running = True
            logger.info(f"Started session: {session_name} ({self.session.session_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            self.stop_session()
            return False

    def stop_session(self) -> bool:
        """Stop the current session.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._running:
            logger.warning("No session running")
            return False

        try:
            # Stop all components
            if self.capture_daemon:
                self.capture_daemon.stop()

            if self.dedup_engine:
                self.dedup_engine.stop()

            if self.storage_manager:
                self.storage_manager.stop()

            self._running = False
            logger.info(f"Stopped session: {self.session.session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop session: {e}")
            return False

    def pause_capture(self) -> bool:
        """Pause capture without stopping the session.

        Returns:
            True if paused successfully, False otherwise
        """
        if not self._running or not self.capture_daemon:
            return False

        return self.capture_daemon.pause()

    def resume_capture(self) -> bool:
        """Resume paused capture.

        Returns:
            True if resumed successfully, False otherwise
        """
        if not self._running or not self.capture_daemon:
            return False

        return self.capture_daemon.resume()

    def set_capture_mode(self, mode: CaptureMode) -> bool:
        """Switch capture mode between IDLE and ACTIVE.

        Args:
            mode: New capture mode

        Returns:
            True if mode switched successfully, False otherwise
        """
        if not self._running or not self.capture_daemon:
            logger.warning("Cannot set mode: capture daemon not running")
            return False

        try:
            self.capture_daemon.set_mode(mode)
            logger.info(f"Capture mode set to: {mode.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to set capture mode: {e}")
            return False

    def get_capture_mode(self) -> Optional[CaptureMode]:
        """Get current capture mode.

        Returns:
            Current capture mode or None if not running
        """
        if not self.capture_daemon:
            return None
        return self.capture_daemon.get_mode()

    def update_session(self, new_session: Session) -> bool:
        """Update the current session (for switching between talks).

        Args:
            new_session: New session object

        Returns:
            True if updated successfully, False otherwise
        """
        if not self._running:
            logger.warning("Cannot update session: orchestrator not running")
            return False

        try:
            # Update session in orchestrator
            old_session_id = self.session.session_id if self.session else None
            self.session = new_session

            # Update session in storage manager
            if self.storage_manager:
                self.storage_manager._session = new_session
                logger.info(f"Updated storage manager session from {old_session_id} to {new_session.session_id}")

            # Update session in capture daemon
            if self.capture_daemon:
                self.capture_daemon._session = new_session
                logger.info(f"Updated capture daemon session from {old_session_id} to {new_session.session_id}")

            # Update session in dedup engine
            if self.dedup_engine:
                self.dedup_engine._session = new_session
                logger.info(f"Updated dedup engine session from {old_session_id} to {new_session.session_id}")

            logger.info(f"Session updated successfully: {new_session.name} ({new_session.session_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            return False

    def is_running(self) -> bool:
        """Check if a session is running.

        Returns:
            True if running, False otherwise
        """
        return self._running

    def get_statistics(self) -> dict:
        """Get statistics from all components.

        Returns:
            Dictionary containing statistics
        """
        stats = {
            "running": self._running,
            "session": None,
            "capture": None,
            "deduplication": None,
            "storage": None
        }

        if self.session:
            stats["session"] = {
                "session_id": self.session.session_id,
                "name": self.session.name,
                "status": self.session.status
            }

        if self.capture_daemon:
            stats["capture"] = self.capture_daemon.get_stats()

        if self.dedup_engine:
            stats["deduplication"] = self.dedup_engine.get_statistics()

        if self.storage_manager:
            stats["storage"] = self.storage_manager.get_statistics()

        return stats

    def _create_dedup_strategy(self, config: dict):
        """Create deduplication strategy based on configuration.

        Args:
            config: Deduplication configuration

        Returns:
            Deduplication strategy instance
        """
        strategy_name = config.get("strategy", "hash")

        if strategy_name == "hash":
            strategy = HashDeduplicationStrategy()
        elif strategy_name == "perceptual":
            strategy = PerceptualDeduplicationStrategy()
        elif strategy_name == "hybrid":
            strategy = HybridDeduplicationStrategy()
        else:
            logger.warning(f"Unknown strategy '{strategy_name}', using hash")
            strategy = HashDeduplicationStrategy()

        strategy.initialize(config)
        return strategy
