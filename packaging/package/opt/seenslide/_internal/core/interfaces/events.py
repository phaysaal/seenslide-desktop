"""Event definitions for the SeenSlide event bus."""

from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict
import time


class EventType(Enum):
    """Enumeration of all event types in the system."""

    # Session events
    SESSION_CREATED = "session.created"
    SESSION_STARTED = "session.started"
    SESSION_PAUSED = "session.paused"
    SESSION_STOPPED = "session.stopped"

    # Capture events
    SLIDE_CAPTURED = "slide.captured"
    CAPTURE_FAILED = "capture.failed"

    # Dedup events
    SLIDE_DUPLICATE = "slide.duplicate"
    SLIDE_UNIQUE = "slide.unique"

    # Storage events
    SLIDE_STORED = "slide.stored"
    STORAGE_ERROR = "storage.error"

    # Server events
    CLIENT_CONNECTED = "client.connected"
    CLIENT_DISCONNECTED = "client.disconnected"

    # Error events
    ERROR_OCCURRED = "error.occurred"


@dataclass
class Event:
    """Represents an event in the system.

    Attributes:
        type: The type of event
        data: Dictionary containing event-specific data
        timestamp: Unix timestamp when event was created
        source: String identifying the source module/component
    """
    type: EventType
    data: Dict[str, Any]
    timestamp: float = None
    source: str = "unknown"

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()
