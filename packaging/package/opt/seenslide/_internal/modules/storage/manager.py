"""Storage manager for coordinating file and metadata storage."""

import logging
from typing import Optional
from PIL import Image
import tempfile

from core.bus.event_bus import EventBus
from core.interfaces.events import Event, EventType
from core.models.slide import ProcessedSlide, RawCapture
from core.models.session import Session
from modules.storage.providers.filesystem_provider import FilesystemStorageProvider
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider
from modules.storage.providers.cloud_provider import CloudStorageProvider

logger = logging.getLogger(__name__)


class StorageManager:
    """Manager for coordinating file and metadata storage.

    The storage manager subscribes to SLIDE_UNIQUE events, saves both
    the image file and metadata, and publishes SLIDE_STORED events.
    """

    def __init__(
        self,
        session: Session,
        config: dict,
        event_bus: Optional[EventBus] = None
    ):
        """Initialize the storage manager.

        Args:
            session: Session configuration
            config: Storage configuration
            event_bus: Event bus for publishing events (None = create new)
        """
        self._session = session
        self._config = config
        self._event_bus = event_bus or EventBus()

        # Initialize providers
        self._filesystem = FilesystemStorageProvider()
        self._database = SQLiteStorageProvider()
        self._cloud = CloudStorageProvider()

        self._running = False
        self._slides_stored = 0
        self._current_talk_id: Optional[str] = None

        logger.info(
            f"StorageManager initialized for session: {session.session_id}"
        )

    def set_current_talk(self, talk_id: Optional[str]) -> None:
        """Set the ID of the current talk for slide association.

        Args:
            talk_id: UUID of the current talk or None
        """
        self._current_talk_id = talk_id
        if talk_id:
            logger.info(f"StorageManager current talk set to: {talk_id}")
        else:
            logger.info("StorageManager current talk cleared")

    def start(self) -> bool:
        """Start the storage manager.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning("Storage manager already running")
            return False

        try:
            # Initialize providers
            if not self._filesystem.initialize(self._config):
                logger.error("Failed to initialize filesystem provider")
                return False

            if not self._database.initialize(self._config):
                logger.error("Failed to initialize database provider")
                return False

            # Initialize cloud provider if cloud config exists
            cloud_config = self._config.get("cloud", {})
            if cloud_config:
                self._cloud.initialize(cloud_config)

            # Use existing cloud session if provided, otherwise create new one
            existing_cloud_session_id = cloud_config.get("existing_session_id")
            admin_username = cloud_config.get("admin_username")
            admin_password_hash = cloud_config.get("admin_password_hash")

            # Reuse existing local session if one already exists for this cloud collection
            reused_local = False
            if existing_cloud_session_id:
                existing_locals = self._database.get_sessions_by_cloud_session(existing_cloud_session_id)
                if existing_locals:
                    # Reuse the most recent local session
                    reused = existing_locals[0]
                    self._session.session_id = reused.session_id
                    self._session.cloud_session_id = reused.cloud_session_id
                    self._session.start_time = reused.start_time
                    self._session.total_slides = reused.total_slides
                    reused_local = True
                    logger.info(f"Reusing existing local session {reused.session_id} for cloud {existing_cloud_session_id}")

            if not reused_local:
                # Create new local session only if none exists for this cloud collection
                self._filesystem.create_session(self._session)
                self._database.create_session(self._session)

            if existing_cloud_session_id and self._cloud.enabled:
                # Bind the cloud provider to the requested session. We don't
                # let session_exists's `False` cause a re-link — its False
                # is ambiguous (could be a 5s network timeout, an auth blip,
                # or a genuine 404). Silently creating a replacement and
                # rewriting the local session row to point at it has caused
                # data-loss-looking incidents where a user's existing talks
                # appear to "vanish" under a new "Unknown" cloud session.
                # If subsequent operations (slide upload, create_talk) hit
                # an actual 404 from the cloud, those paths log it and
                # degrade gracefully without rebinding.
                self._cloud.cloud_session_id = existing_cloud_session_id
                if self._cloud.session_exists(existing_cloud_session_id):
                    logger.info(
                        f"Verified existing cloud collection: {existing_cloud_session_id}"
                    )
                else:
                    logger.warning(
                        f"Could not verify cloud session {existing_cloud_session_id} "
                        f"(may be a transient error). Using it anyway."
                    )

            # We DO NOT auto-create a cloud session at boot when none is
            # specified. The user creates sessions explicitly via the
            # "+New" button in the Sessions tab (which uses
            # CloudSessionsClient directly, not this code path) or when
            # they click "Start Presenting" while no current collection
            # is set (handled in main_dashboard._start_recording_after_countdown).
            # Creating one here generated phantom "Unknown" sessions on every
            # launch that didn't pass an existing_session_id.

            # If the cloud provider got a session id (from the verified-or-
            # accepted-anyway branch above), reflect it on the local row.
            # Skip this when cloud_session_id wasn't set — leaves the
            # existing value intact rather than nulling it.
            if (
                self._cloud.enabled
                and self._cloud.cloud_session_id
                and self._cloud.cloud_session_id != self._session.cloud_session_id
            ):
                self._session.cloud_session_id = self._cloud.cloud_session_id
                self._database.update_session(self._session)
                logger.info(
                    f"Linked local session {self._session.session_id} to "
                    f"cloud {self._cloud.cloud_session_id}"
                )

            # Subscribe to SLIDE_UNIQUE events
            self._event_bus.subscribe(
                EventType.SLIDE_UNIQUE,
                self._handle_slide_unique
            )

            self._running = True
            logger.info("Storage manager started")
            return True

        except Exception as e:
            logger.error(f"Failed to start storage manager: {e}")
            return False

    def stop(self) -> bool:
        """Stop the storage manager.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._running:
            logger.warning("Storage manager not running")
            return False

        try:
            # Unsubscribe from events
            self._event_bus.unsubscribe(
                EventType.SLIDE_UNIQUE,
                self._handle_slide_unique
            )

            # Update session with final count
            self._session.total_slides = self._slides_stored
            self._database.update_session(self._session)

            # Cleanup providers
            self._filesystem.cleanup()
            self._database.cleanup()
            self._cloud.cleanup()

            self._running = False
            logger.info(
                f"Storage manager stopped. Stored {self._slides_stored} slides"
            )
            return True

        except Exception as e:
            logger.error(f"Error stopping storage manager: {e}")
            return False

    def is_running(self) -> bool:
        """Check if manager is running.

        Returns:
            True if running, False otherwise
        """
        return self._running

    def get_statistics(self) -> dict:
        """Get storage statistics.

        Returns:
            Dictionary containing statistics
        """
        return {
            "slides_stored": self._slides_stored,
            "session_id": self._session.session_id,
            "running": self._running,
        }

    def _handle_slide_unique(self, event: Event) -> None:
        """Handle SLIDE_UNIQUE event.

        Args:
            event: SLIDE_UNIQUE event containing capture data
        """
        try:
            # Extract capture from event data
            capture: RawCapture = event.data.get("capture")
            if not capture:
                logger.error("No capture in SLIDE_UNIQUE event")
                return

            # Only process slides for our session
            session_id = event.data.get("session_id")
            if session_id != self._session.session_id:
                logger.debug(f"Ignoring slide from different session: {session_id}")
                return

            # Get sequence number and other data
            sequence_number = event.data.get("sequence_number", 0)
            similarity_score = event.data.get("similarity_score", 0.0)

            # Save the slide
            self._save_slide(capture, sequence_number, similarity_score)

        except Exception as e:
            logger.error(f"Error handling slide unique: {e}", exc_info=True)

            # Publish error event
            self._event_bus.publish(Event(
                type=EventType.STORAGE_ERROR,
                data={
                    "error": str(e),
                    "source": "storage_manager",
                },
                source="storage_manager"
            ))

    def _save_slide(
        self,
        capture: RawCapture,
        sequence_number: int,
        similarity_score: float
    ) -> None:
        """Save a slide to storage.

        Args:
            capture: Raw capture to save
            sequence_number: Sequence number in session
            similarity_score: Similarity score vs previous slide
        """
        try:
            # Create ProcessedSlide object
            slide = ProcessedSlide(
                session_id=self._session.session_id,
                talk_id=self._current_talk_id or "",
                timestamp=capture.timestamp,
                sequence_number=sequence_number,
                width=capture.width,
                height=capture.height,
                similarity_score=similarity_score,
                metadata=capture.metadata
            )

            # Save image to temporary file first (for filesystem provider)
            import os
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                capture.image.save(tmp_path, "PNG")
                slide.image_path = tmp_path

            try:
                # Save to filesystem (this updates slide.image_path and slide.thumbnail_path)
                self._filesystem.save_slide(slide)
            finally:
                # Clean up temporary file
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass

            # Save to database
            self._database.save_slide(slide)

            # Upload to cloud if enabled
            try:
                import io
                # JPEG for cloud upload to save bandwidth. Quality 75 balances
                # bandwidth vs visible artifacts on screen-content captures —
                # text stays readable, slide backgrounds stay clean.
                img_byte_arr = io.BytesIO()
                capture.image.convert('RGB').save(img_byte_arr, format='JPEG', quality=75, optimize=True)
                img_byte_arr.seek(0)
                self._cloud.save_slide(slide, img_byte_arr.getvalue())
            except Exception as e:
                logger.warning(f"Failed to upload slide to cloud: {e}")

            self._slides_stored += 1

            # Publish SLIDE_STORED event
            self._event_bus.publish(Event(
                type=EventType.SLIDE_STORED,
                data={
                    "session_id": self._session.session_id,
                    "slide_id": slide.slide_id,
                    "slide": slide,
                    "sequence_number": sequence_number,
                    "timestamp": capture.timestamp,
                },
                source="storage_manager"
            ))

            logger.info(
                f"Stored slide #{sequence_number}: {slide.slide_id}"
            )

        except Exception as e:
            logger.error(f"Failed to save slide: {e}", exc_info=True)
            raise

    def get_session(self) -> Session:
        """Get the current session.

        Returns:
            Session object
        """
        return self._session

    def get_slides(self, limit: Optional[int] = None, offset: int = 0) -> list:
        """Get slides for the current session.

        Args:
            limit: Maximum number of slides to return
            offset: Number of slides to skip

        Returns:
            List of ProcessedSlide objects
        """
        if not self._running:
            return []

        return self._database.list_slides(
            self._session.session_id,
            limit=limit,
            offset=offset
        )
