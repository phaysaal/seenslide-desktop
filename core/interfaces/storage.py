"""Interface for storage providers."""

from abc import ABC, abstractmethod
from typing import Optional, List
from core.models.slide import ProcessedSlide
from core.models.session import Session


class IStorageProvider(ABC):
    """Interface for storage providers.

    This abstract base class defines the contract for all storage providers
    (filesystem, database, cloud, etc.).
    """

    @abstractmethod
    def initialize(self, config: dict) -> bool:
        """Initialize storage provider with configuration.

        Args:
            config: Dictionary containing provider-specific configuration

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def create_session(self, session: Session) -> str:
        """Create a new session.

        Args:
            session: Session object to create

        Returns:
            Session ID (UUID string)

        Raises:
            StorageError: If session creation fails
        """
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session by ID.

        Args:
            session_id: UUID of the session

        Returns:
            Session object or None if not found
        """
        pass

    @abstractmethod
    def update_session(self, session: Session) -> bool:
        """Update an existing session.

        Args:
            session: Session object with updated data

        Returns:
            True if update successful, False otherwise
        """
        pass

    @abstractmethod
    def save_slide(self, slide: ProcessedSlide) -> str:
        """Save a processed slide.

        Args:
            slide: ProcessedSlide object to save

        Returns:
            Slide ID (UUID string)

        Raises:
            StorageError: If save fails
        """
        pass

    @abstractmethod
    def get_slide(self, slide_id: str) -> Optional[ProcessedSlide]:
        """Retrieve slide by ID.

        Args:
            slide_id: UUID of the slide

        Returns:
            ProcessedSlide object or None if not found
        """
        pass

    @abstractmethod
    def list_slides(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[ProcessedSlide]:
        """List slides for a session.

        Args:
            session_id: UUID of the session
            limit: Maximum number of slides to return (None = all)
            offset: Number of slides to skip

        Returns:
            List of ProcessedSlide objects
        """
        pass

    @abstractmethod
    def get_slide_count(self, session_id: str) -> int:
        """Get total slide count for session.

        Args:
            session_id: UUID of the session

        Returns:
            Total number of slides in the session
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources used by storage provider."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'filesystem', 'sqlite')."""
        pass


class StorageError(Exception):
    """Exception raised when storage operations fail."""
    pass
