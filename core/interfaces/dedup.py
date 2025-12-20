"""Interface for deduplication strategies."""

from abc import ABC, abstractmethod
from core.models.slide import RawCapture


class IDeduplicationStrategy(ABC):
    """Interface for deduplication strategies.

    This abstract base class defines the contract for all deduplication
    strategies (hash-based, perceptual, LLM-based, hybrid).
    """

    @abstractmethod
    def initialize(self, config: dict) -> bool:
        """Initialize the strategy with configuration.

        Args:
            config: Dictionary containing strategy-specific configuration

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def is_duplicate(self, current: RawCapture, previous: RawCapture) -> bool:
        """Check if current capture is duplicate of previous.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against

        Returns:
            True if duplicate, False if unique
        """
        pass

    @abstractmethod
    def get_similarity_score(self) -> float:
        """Get similarity score from last comparison.

        Returns:
            Float 0.0-1.0 where:
            - 0.0 = completely different
            - 1.0 = identical
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name (e.g., 'hash', 'perceptual', 'hybrid')."""
        pass

    @property
    @abstractmethod
    def avg_processing_time_ms(self) -> float:
        """Average processing time in milliseconds."""
        pass


class DeduplicationError(Exception):
    """Exception raised when deduplication fails."""
    pass
