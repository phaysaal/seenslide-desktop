"""Filesystem-based storage provider for slide images."""

import logging
import os
from pathlib import Path
from typing import Optional
from PIL import Image

from core.interfaces.storage import IStorageProvider, StorageError
from core.models.slide import ProcessedSlide
from core.models.session import Session

logger = logging.getLogger(__name__)


class FilesystemStorageProvider(IStorageProvider):
    """Storage provider that saves images to the filesystem.

    This provider handles:
    - Saving full-size slide images
    - Generating and saving thumbnails
    - Organizing files by session
    """

    def __init__(self):
        """Initialize the filesystem storage provider."""
        self._config = {}
        self._initialized = False
        self._base_path = None
        self._images_path = None
        self._thumbnails_path = None

    def initialize(self, config: dict) -> bool:
        """Initialize storage provider with configuration.

        Args:
            config: Dictionary containing configuration:
                - base_path: str, base directory for storage
                - images_subdir: str, subdirectory for images (default: 'images')
                - thumbnails_subdir: str, subdirectory for thumbnails (default: 'thumbnails')
                - create_thumbnails: bool, whether to create thumbnails (default: True)
                - thumbnail_width: int, thumbnail width in pixels (default: 320)
                - thumbnail_quality: int, JPEG quality for thumbnails (default: 85)

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config

            # Get paths
            self._base_path = Path(config.get('base_path', '/tmp/seenslide'))
            images_subdir = config.get('images_subdir', 'images')
            thumbnails_subdir = config.get('thumbnails_subdir', 'thumbnails')

            self._images_path = self._base_path / images_subdir
            self._thumbnails_path = self._base_path / thumbnails_subdir

            # Get options
            self._create_thumbnails = config.get('create_thumbnails', True)
            self._thumbnail_width = config.get('thumbnail_width', 320)
            self._thumbnail_quality = config.get('thumbnail_quality', 85)

            # Create directories
            self._images_path.mkdir(parents=True, exist_ok=True)
            self._thumbnails_path.mkdir(parents=True, exist_ok=True)

            self._initialized = True
            logger.info(f"Filesystem storage initialized at: {self._base_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize filesystem storage: {e}")
            return False

    def create_session(self, session: Session) -> str:
        """Create a new session (creates session directories).

        Args:
            session: Session object to create

        Returns:
            Session ID

        Raises:
            StorageError: If session creation fails
        """
        if not self._initialized:
            raise StorageError("Provider not initialized")

        try:
            # Create session subdirectories
            session_images_dir = self._images_path / session.session_id
            session_thumbnails_dir = self._thumbnails_path / session.session_id

            session_images_dir.mkdir(parents=True, exist_ok=True)
            session_thumbnails_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Created session directories for: {session.session_id}")
            return session.session_id

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise StorageError(f"Failed to create session: {e}")

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session by ID.

        Note: Filesystem provider doesn't store session metadata.
        This should be handled by a database provider.

        Args:
            session_id: UUID of the session

        Returns:
            None (not implemented for filesystem provider)
        """
        # Filesystem provider doesn't store session metadata
        return None

    def update_session(self, session: Session) -> bool:
        """Update an existing session.

        Note: Filesystem provider doesn't store session metadata.

        Args:
            session: Session object with updated data

        Returns:
            True (no-op for filesystem provider)
        """
        # Filesystem provider doesn't store session metadata
        return True

    def save_slide(self, slide: ProcessedSlide) -> str:
        """Save a processed slide to filesystem.

        Args:
            slide: ProcessedSlide object to save

        Returns:
            Slide ID

        Raises:
            StorageError: If save fails
        """
        if not self._initialized:
            raise StorageError("Provider not initialized")

        try:
            # Determine paths
            session_images_dir = self._images_path / slide.session_id
            session_thumbnails_dir = self._thumbnails_path / slide.session_id

            # Ensure directories exist
            session_images_dir.mkdir(parents=True, exist_ok=True)
            session_thumbnails_dir.mkdir(parents=True, exist_ok=True)

            # Save full-size image
            image_filename = f"{slide.slide_id}.png"
            image_path = session_images_dir / image_filename

            # Load image from existing path if available
            if slide.image_path and os.path.exists(slide.image_path):
                image = Image.open(slide.image_path)
            else:
                raise StorageError("No image data available to save")

            image.save(image_path, "PNG")
            slide.image_path = str(image_path)
            slide.file_size_bytes = image_path.stat().st_size

            logger.debug(f"Saved slide image: {image_path}")

            # Generate and save thumbnail
            if self._create_thumbnails:
                thumbnail_filename = f"{slide.slide_id}.jpg"
                thumbnail_path = session_thumbnails_dir / thumbnail_filename

                # Create thumbnail
                thumbnail = image.copy()
                aspect_ratio = thumbnail.height / thumbnail.width
                thumbnail_height = int(self._thumbnail_width * aspect_ratio)
                thumbnail.thumbnail((self._thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)
                thumbnail.save(thumbnail_path, "JPEG", quality=self._thumbnail_quality)

                slide.thumbnail_path = str(thumbnail_path)
                logger.debug(f"Saved thumbnail: {thumbnail_path}")

            return slide.slide_id

        except Exception as e:
            logger.error(f"Failed to save slide: {e}")
            raise StorageError(f"Failed to save slide: {e}")

    def get_slide(self, slide_id: str) -> Optional[ProcessedSlide]:
        """Retrieve slide by ID.

        Note: Filesystem provider doesn't store slide metadata.

        Args:
            slide_id: UUID of the slide

        Returns:
            None (not implemented for filesystem provider)
        """
        # Filesystem provider doesn't store slide metadata
        return None

    def list_slides(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list:
        """List slides for a session.

        Note: Filesystem provider doesn't store slide metadata.

        Args:
            session_id: UUID of the session
            limit: Maximum number of slides to return
            offset: Number of slides to skip

        Returns:
            Empty list (not implemented for filesystem provider)
        """
        # Filesystem provider doesn't store slide metadata
        return []

    def get_slide_count(self, session_id: str) -> int:
        """Get total slide count for session.

        Args:
            session_id: UUID of the session

        Returns:
            Number of slide images found in filesystem
        """
        if not self._initialized:
            return 0

        try:
            session_images_dir = self._images_path / session_id
            if not session_images_dir.exists():
                return 0

            # Count PNG files
            return len(list(session_images_dir.glob("*.png")))

        except Exception as e:
            logger.error(f"Failed to count slides: {e}")
            return 0

    def cleanup(self) -> None:
        """Clean up resources."""
        self._initialized = False
        logger.debug("Filesystem storage cleaned up")

    @property
    def name(self) -> str:
        """Provider name."""
        return "filesystem"

    def delete_session(self, session_id: str) -> bool:
        """Delete all files for a session.

        Args:
            session_id: UUID of the session to delete

        Returns:
            True if deletion successful, False otherwise
        """
        if not self._initialized:
            return False

        try:
            import shutil

            session_images_dir = self._images_path / session_id
            session_thumbnails_dir = self._thumbnails_path / session_id

            if session_images_dir.exists():
                shutil.rmtree(session_images_dir)
                logger.info(f"Deleted session images: {session_id}")

            if session_thumbnails_dir.exists():
                shutil.rmtree(session_thumbnails_dir)
                logger.info(f"Deleted session thumbnails: {session_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False
