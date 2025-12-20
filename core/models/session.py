"""Data models for presentation sessions."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import uuid


@dataclass
class Session:
    """Represents a presentation session.

    A session represents a single presentation or talk where slides are
    being captured and made available to the audience.

    Attributes:
        session_id: Unique identifier for this session
        name: Human-readable name for the session
        description: Detailed description of the session
        presenter_name: Name of the presenter
        start_time: Unix timestamp when session started
        end_time: Unix timestamp when session ended
        status: Current status (created, active, paused, completed)
        total_slides: Number of unique slides captured
        capture_interval_seconds: How often to capture (e.g., 2.0)
        dedup_strategy: Which deduplication strategy to use
        metadata: Additional metadata
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    presenter_name: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    status: str = "created"  # created, active, paused, completed
    total_slides: int = 0
    capture_interval_seconds: float = 2.0
    dedup_strategy: str = "hash"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if session is currently active.

        Returns:
            True if status is 'active', False otherwise
        """
        return self.status == "active"

    def is_completed(self) -> bool:
        """Check if session is completed.

        Returns:
            True if status is 'completed', False otherwise
        """
        return self.status == "completed"

    def duration_seconds(self) -> Optional[float]:
        """Get duration of the session in seconds.

        Returns:
            Duration in seconds, or None if session hasn't ended
        """
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the session
        """
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "presenter_name": self.presenter_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "total_slides": self.total_slides,
            "capture_interval_seconds": self.capture_interval_seconds,
            "dedup_strategy": self.dedup_strategy,
            "metadata": self.metadata,
        }
