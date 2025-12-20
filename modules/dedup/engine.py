"""Deduplication engine for processing captured slides."""

import logging
from typing import Optional, Dict, Any

from core.bus.event_bus import EventBus
from core.interfaces.events import Event, EventType
from core.interfaces.dedup import IDeduplicationStrategy
from core.models.slide import RawCapture
from core.models.session import Session

logger = logging.getLogger(__name__)


class DeduplicationEngine:
    """Engine for deduplicating captured slides.

    The deduplication engine subscribes to SLIDE_CAPTURED events, compares
    each new slide with the previous one using the configured strategy, and
    publishes SLIDE_UNIQUE or SLIDE_DUPLICATE events accordingly.
    """

    def __init__(
        self,
        strategy: IDeduplicationStrategy,
        session: Session,
        event_bus: Optional[EventBus] = None
    ):
        """Initialize the deduplication engine.

        Args:
            strategy: Initialized deduplication strategy
            session: Session configuration
            event_bus: Event bus for publishing events (None = create new)
        """
        self._strategy = strategy
        self._session = session
        self._event_bus = event_bus or EventBus()

        self._previous_capture: Optional[RawCapture] = None
        self._running = False

        # Statistics
        self._total_captures = 0
        self._unique_slides = 0
        self._duplicate_slides = 0

        logger.info(
            f"DeduplicationEngine initialized for session: {session.session_id} "
            f"with strategy: {strategy.name}"
        )

    def start(self) -> bool:
        """Start the deduplication engine.

        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning("Deduplication engine already running")
            return False

        try:
            # Subscribe to SLIDE_CAPTURED events
            self._event_bus.subscribe(
                EventType.SLIDE_CAPTURED,
                self._handle_slide_captured
            )

            self._running = True
            logger.info("Deduplication engine started")
            return True

        except Exception as e:
            logger.error(f"Failed to start deduplication engine: {e}")
            return False

    def stop(self) -> bool:
        """Stop the deduplication engine.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._running:
            logger.warning("Deduplication engine not running")
            return False

        try:
            # Unsubscribe from events
            self._event_bus.unsubscribe(
                EventType.SLIDE_CAPTURED,
                self._handle_slide_captured
            )

            self._running = False
            logger.info(
                f"Deduplication engine stopped. "
                f"Stats: {self._unique_slides} unique, "
                f"{self._duplicate_slides} duplicates"
            )
            return True

        except Exception as e:
            logger.error(f"Error stopping deduplication engine: {e}")
            return False

    def is_running(self) -> bool:
        """Check if engine is running.

        Returns:
            True if running, False otherwise
        """
        return self._running

    def get_statistics(self) -> Dict[str, Any]:
        """Get deduplication statistics.

        Returns:
            Dictionary containing statistics
        """
        return {
            "total_captures": self._total_captures,
            "unique_slides": self._unique_slides,
            "duplicate_slides": self._duplicate_slides,
            "duplicate_rate": (
                self._duplicate_slides / self._total_captures
                if self._total_captures > 0 else 0.0
            ),
            "strategy": self._strategy.name,
            "strategy_stats": self._strategy.get_statistics()
            if hasattr(self._strategy, 'get_statistics') else {},
            "running": self._running,
        }

    def _handle_slide_captured(self, event: Event) -> None:
        """Handle SLIDE_CAPTURED event.

        Args:
            event: SLIDE_CAPTURED event containing capture data
        """
        try:
            # Extract capture from event data
            capture: RawCapture = event.data.get("capture")
            if not capture:
                logger.error("No capture in SLIDE_CAPTURED event")
                return

            # Only process captures for our session
            session_id = event.data.get("session_id")
            if session_id != self._session.session_id:
                logger.debug(f"Ignoring capture from different session: {session_id}")
                return

            self._total_captures += 1

            # First capture is always unique
            if self._previous_capture is None:
                self._mark_as_unique(capture, event)
                self._previous_capture = capture
                return

            # Compare with previous
            is_duplicate = self._strategy.is_duplicate(capture, self._previous_capture)
            similarity_score = self._strategy.get_similarity_score()

            if is_duplicate:
                self._mark_as_duplicate(capture, event, similarity_score)
            else:
                self._mark_as_unique(capture, event, similarity_score)
                self._previous_capture = capture

        except Exception as e:
            logger.error(f"Error handling slide capture: {e}", exc_info=True)

            # Publish error event
            self._event_bus.publish(Event(
                type=EventType.ERROR_OCCURRED,
                data={
                    "error": str(e),
                    "source": "dedup_engine",
                    "capture_id": capture.capture_id if capture else None,
                },
                source="dedup_engine"
            ))

    def _mark_as_unique(
        self,
        capture: RawCapture,
        original_event: Event,
        similarity_score: float = 0.0
    ) -> None:
        """Mark a capture as unique and publish event.

        Args:
            capture: The unique capture
            original_event: Original SLIDE_CAPTURED event
            similarity_score: Similarity score vs previous (0.0 for first slide)
        """
        self._unique_slides += 1

        # Publish SLIDE_UNIQUE event
        self._event_bus.publish(Event(
            type=EventType.SLIDE_UNIQUE,
            data={
                "session_id": self._session.session_id,
                "capture_id": capture.capture_id,
                "capture": capture,
                "sequence_number": self._unique_slides,
                "similarity_score": similarity_score,
                "strategy": self._strategy.name,
                "timestamp": capture.timestamp,
            },
            source="dedup_engine"
        ))

        logger.debug(
            f"Slide marked as UNIQUE: {capture.capture_id} "
            f"(#{self._unique_slides}, similarity: {similarity_score:.4f})"
        )

    def _mark_as_duplicate(
        self,
        capture: RawCapture,
        original_event: Event,
        similarity_score: float
    ) -> None:
        """Mark a capture as duplicate and publish event.

        Args:
            capture: The duplicate capture
            original_event: Original SLIDE_CAPTURED event
            similarity_score: Similarity score vs previous
        """
        self._duplicate_slides += 1

        # Publish SLIDE_DUPLICATE event
        self._event_bus.publish(Event(
            type=EventType.SLIDE_DUPLICATE,
            data={
                "session_id": self._session.session_id,
                "capture_id": capture.capture_id,
                "similarity_score": similarity_score,
                "strategy": self._strategy.name,
                "timestamp": capture.timestamp,
            },
            source="dedup_engine"
        ))

        logger.debug(
            f"Slide marked as DUPLICATE: {capture.capture_id} "
            f"(similarity: {similarity_score:.4f})"
        )
