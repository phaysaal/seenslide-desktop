"""Data models for slides and captures."""

from dataclasses import dataclass, field
from typing import Dict, Any
from PIL import Image
import uuid


@dataclass
class RawCapture:
    """Raw captured screenshot before processing.

    This represents a screenshot that has just been captured and hasn't
    yet been processed or deduplicated.

    Attributes:
        image: PIL Image object containing the captured screenshot
        timestamp: Unix timestamp when capture occurred
        monitor_id: Which monitor was captured
        width: Image width in pixels
        height: Image height in pixels
        capture_id: Unique identifier for this capture
        metadata: Additional metadata (provider, settings, etc.)
    """
    image: Image.Image
    timestamp: float
    monitor_id: int
    width: int
    height: int
    capture_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedSlide:
    """Processed slide after deduplication and storage.

    This represents a unique slide that has been determined to be different
    from previous slides and has been saved to storage.

    Attributes:
        slide_id: Unique identifier for this slide
        session_id: ID of the session this slide belongs to
        image_path: File path to the saved full-size image
        thumbnail_path: File path to the thumbnail image
        timestamp: Unix timestamp when slide was captured
        sequence_number: Order in the session (1, 2, 3, ...)
        width: Image width in pixels
        height: Image height in pixels
        file_size_bytes: Size of the saved image file
        image_hash: Hash of the image for quick comparison
        similarity_score: Similarity score vs previous slide (0.0-1.0)
        metadata: Additional metadata
    """
    slide_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    image_path: str = ""
    thumbnail_path: str = ""
    timestamp: float = 0.0
    sequence_number: int = 0
    width: int = 0
    height: int = 0
    file_size_bytes: int = 0
    image_hash: str = ""
    similarity_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the slide
        """
        return {
            "slide_id": self.slide_id,
            "session_id": self.session_id,
            "image_path": self.image_path,
            "thumbnail_path": self.thumbnail_path,
            "timestamp": self.timestamp,
            "sequence_number": self.sequence_number,
            "width": self.width,
            "height": self.height,
            "file_size_bytes": self.file_size_bytes,
            "image_hash": self.image_hash,
            "similarity_score": self.similarity_score,
            "metadata": self.metadata,
        }
