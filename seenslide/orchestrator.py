"""Main orchestrator for SeenSlide system."""

import logging
import threading
from typing import Optional, Dict
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
from modules.dedup.strategies.adaptive_strategy import AdaptiveDeduplicationStrategy
from modules.storage.manager import StorageManager
from modules.voice.recorder import VoiceRecorder
from modules.voice.cloud_uploader import VoiceCloudUploader
from core.interfaces.events import EventType

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
        self.voice_recorder: Optional[VoiceRecorder] = None
        self._voice_cloud_uploader: Optional[VoiceCloudUploader] = None
        self._voice_auto_chunk_timer: Optional[threading.Timer] = None

        self._voice_enabled = False
        self._running = False

        logger.info("SeenSlide orchestrator initialized")

    def start_session(
        self,
        session_name: str,
        description: str = "",
        presenter_name: str = "",
        monitor_id: int = 1,
        mode: CaptureMode = CaptureMode.ACTIVE,
        crop_region: Optional[Dict[str, int]] = None
    ) -> bool:
        """Start a new capture session.

        Args:
            session_name: Name of the session
            description: Session description
            presenter_name: Name of presenter
            monitor_id: Monitor to capture from
            mode: Capture mode (IDLE or ACTIVE)
            crop_region: Optional region for deduplication.
                        Format: {"x": int, "y": int, "width": int, "height": int}
                        If None, full images are compared

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
            strategy = self._create_dedup_strategy(dedup_config, capture_provider)
            self.dedup_engine = DeduplicationEngine(
                strategy=strategy,
                session=self.session,
                event_bus=self.event_bus,
                crop_region=crop_region
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
            # Stop voice recording first (before other components)
            self.stop_voice_recording()

            # Stop all components
            if self.capture_daemon:
                self.capture_daemon.stop()

            if self.dedup_engine:
                self.dedup_engine.stop()

            if self.storage_manager:
                self.storage_manager.stop()

            self._running = False
            session_id = self.session.session_id if self.session else "unknown"
            logger.info(f"Stopped session: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop session: {e}")
            return False

    # ------------------------------------------------------------------
    # Voice recording
    # ------------------------------------------------------------------

    def set_voice_enabled(self, enabled: bool, device: int = None):
        """Enable or disable voice recording for subsequent talks.

        Args:
            enabled: Whether to record audio during talks.
            device: Audio input device index (None = system default).
        """
        self._voice_enabled = enabled
        self._voice_device = device
        logger.info(f"Voice recording {'enabled' if enabled else 'disabled'}")

    def start_voice_recording(self) -> bool:
        """Start recording voice (call after talk has started).

        Starts local WAV recording and, if cloud is configured,
        starts a cloud recording + subscribes to SLIDE_UNIQUE for
        semi-live chunk uploads.

        Returns:
            True if recording started successfully.
        """
        if not self._voice_enabled:
            return False

        if not self._running or not self.session:
            logger.warning("Cannot record voice: no active session")
            return False

        # Determine output directory (next to slides)
        storage_cfg = self.config.get("storage", {})
        base = storage_cfg.get("base_path", "~/.local/share/seenslide")
        from pathlib import Path
        output_dir = Path(base).expanduser() / "voice"

        self.voice_recorder = VoiceRecorder(
            event_bus=self.event_bus,
            output_dir=str(output_dir),
            session_id=self.session.session_id,
            device=getattr(self, '_voice_device', None),
        )

        if not self.voice_recorder.start():
            return False

        # Start cloud voice upload if cloud is configured
        cloud_cfg = self.config.get("cloud", {})
        api_url = cloud_cfg.get("api_url", "").rstrip("/")
        cloud_session_id = getattr(self.session, 'cloud_session_id', None)

        if api_url and cloud_session_id:
            self._voice_cloud_uploader = VoiceCloudUploader(
                api_url=api_url,
                session_token=cloud_cfg.get("session_token", ""),
            )
            ok = self._voice_cloud_uploader.start_cloud_recording(cloud_session_id)
            if ok:
                # Subscribe to slide events for chunk uploads
                self.event_bus.subscribe(
                    EventType.SLIDE_UNIQUE, self._on_slide_for_voice_upload
                )
                # Start 60-second auto-chunk timer (uploads even without slide changes)
                self._start_auto_chunk_timer()
                logger.info("Voice cloud upload enabled (semi-live, 60s auto-chunk)")
            else:
                logger.warning("Cloud voice recording failed to start — recording locally only")
                self._voice_cloud_uploader = None

        return True

    def _on_slide_for_voice_upload(self, event):
        """Flush audio chunk and upload to cloud on each new slide."""
        self._flush_and_upload_voice()
        # Reset auto-chunk timer since we just uploaded
        self._restart_auto_chunk_timer()

    def _flush_and_upload_voice(self):
        """Flush accumulated audio and upload to cloud."""
        if not self.voice_recorder or not self._voice_cloud_uploader:
            return

        chunk = self.voice_recorder.flush_chunk()
        if not chunk:
            return

        markers = self.voice_recorder.markers
        slide_num = markers[-1].slide_number if markers else 0
        ts = markers[-1].timestamp_seconds if markers else 0.0

        self._voice_cloud_uploader.upload_chunk(chunk, slide_num, ts)

    # --- 60-second auto-chunk timer ---

    _AUTO_CHUNK_INTERVAL = 60  # seconds

    def _start_auto_chunk_timer(self):
        """Start repeating timer that uploads audio every 60s."""
        self._voice_auto_chunk_timer = threading.Timer(
            self._AUTO_CHUNK_INTERVAL, self._auto_chunk_tick
        )
        self._voice_auto_chunk_timer.daemon = True
        self._voice_auto_chunk_timer.start()

    def _restart_auto_chunk_timer(self):
        """Reset the timer (called after each slide-triggered upload)."""
        self._stop_auto_chunk_timer()
        if self.voice_recorder and self.voice_recorder.is_recording:
            self._start_auto_chunk_timer()

    def _stop_auto_chunk_timer(self):
        if self._voice_auto_chunk_timer:
            self._voice_auto_chunk_timer.cancel()
            self._voice_auto_chunk_timer = None

    def _auto_chunk_tick(self):
        """Timer callback: upload audio even if no new slide appeared."""
        if self.voice_recorder and self.voice_recorder.is_recording:
            logger.debug("Auto-chunk: uploading audio (no slide change in 60s)")
            self._flush_and_upload_voice()
            # Re-schedule
            self._start_auto_chunk_timer()

    def stop_voice_recording(self) -> Optional[str]:
        """Stop voice recording and return the WAV file path.

        Also uploads any remaining audio chunk and stops the cloud recording.
        """
        # Stop auto-chunk timer
        self._stop_auto_chunk_timer()

        path = None

        if self.voice_recorder and self.voice_recorder.is_recording:
            # Flush final chunk to cloud before stopping
            if self._voice_cloud_uploader:
                final_chunk = self.voice_recorder.flush_chunk()
                if final_chunk:
                    markers = self.voice_recorder.markers
                    slide_num = markers[-1].slide_number if markers else 0
                    ts = markers[-1].timestamp_seconds if markers else 0.0
                    self._voice_cloud_uploader.upload_chunk(final_chunk, slide_num, ts)

            duration = self.voice_recorder.duration_seconds
            path = self.voice_recorder.stop()

            # Finalize cloud recording
            if self._voice_cloud_uploader:
                self._voice_cloud_uploader.stop_cloud_recording(duration)
                self._voice_cloud_uploader = None

                # Unsubscribe from slide events
                self.event_bus.unsubscribe(
                    EventType.SLIDE_UNIQUE, self._on_slide_for_voice_upload
                )

        return path

    def get_voice_stats(self) -> Optional[dict]:
        """Get voice recording statistics."""
        if self.voice_recorder:
            return self.voice_recorder.get_stats()
        return None

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

                # Update cloud provider's cloud_session_id from the new session
                if hasattr(self.storage_manager, '_cloud') and self.storage_manager._cloud:
                    if new_session.cloud_session_id:
                        self.storage_manager._cloud.cloud_session_id = new_session.cloud_session_id
                        logger.info(f"Updated cloud provider to use cloud session: {new_session.cloud_session_id}")

                        # Create talk in cloud session (don't fail if this doesn't work)
                        try:
                            self.storage_manager._cloud.create_talk(
                                session_id=new_session.session_id,
                                talk_name=new_session.name,
                                presenter_name=new_session.presenter_name,
                                description=new_session.description
                            )
                        except Exception as e:
                            logger.warning(f"Failed to create talk in cloud (continuing anyway): {e}")

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
            "storage": None,
            "voice": None,
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

        if self.voice_recorder:
            stats["voice"] = self.voice_recorder.get_stats()

        return stats

    def _create_dedup_strategy(self, config: dict, capture_provider=None):
        """Create deduplication strategy based on configuration.

        Args:
            config: Deduplication configuration
            capture_provider: Capture provider (needed for adaptive strategy)

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
        elif strategy_name == "adaptive":
            strategy = AdaptiveDeduplicationStrategy(capture_provider=capture_provider)
            logger.info("Using adaptive deduplication with region profiling")
        else:
            logger.warning(f"Unknown strategy '{strategy_name}', using hash")
            strategy = HashDeduplicationStrategy()

        strategy.initialize(config)
        return strategy
