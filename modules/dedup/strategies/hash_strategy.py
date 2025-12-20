"""Hash-based deduplication strategy."""

import logging
import hashlib
import time
from typing import Dict, Any

from core.interfaces.dedup import IDeduplicationStrategy, DeduplicationError
from core.models.slide import RawCapture

logger = logging.getLogger(__name__)


class HashDeduplicationStrategy(IDeduplicationStrategy):
    """Hash-based deduplication using MD5/SHA256.

    This strategy compares images by computing cryptographic hashes of the
    raw image data. It's the fastest method and detects only exact duplicates
    (pixel-perfect matches).
    """

    def __init__(self):
        """Initialize the hash deduplication strategy."""
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._last_similarity_score = 0.0
        self._processing_times = []
        self._max_history = 100

    def initialize(self, config: dict) -> bool:
        """Initialize the strategy with configuration.

        Args:
            config: Dictionary containing strategy configuration:
                - hash_algorithm: str, 'md5' or 'sha256' (default: 'md5')

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config
            self._hash_algorithm = config.get('hash_algorithm', 'md5')

            # Validate algorithm
            if self._hash_algorithm not in ['md5', 'sha256']:
                logger.error(f"Invalid hash algorithm: {self._hash_algorithm}")
                return False

            self._initialized = True
            logger.info(
                f"Hash deduplication strategy initialized "
                f"with {self._hash_algorithm}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize hash strategy: {e}")
            return False

    def is_duplicate(self, current: RawCapture, previous: RawCapture) -> bool:
        """Check if current is duplicate of previous using hash comparison.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against

        Returns:
            True if images are identical (hashes match), False otherwise

        Raises:
            DeduplicationError: If comparison fails
        """
        if not self._initialized:
            raise DeduplicationError("Strategy not initialized")

        try:
            start_time = time.time()

            # Compute hashes
            current_hash = self._compute_hash(current.image)
            previous_hash = self._compute_hash(previous.image)

            # Compare hashes
            is_dup = current_hash == previous_hash

            # Update similarity score (1.0 if identical, 0.0 if different)
            self._last_similarity_score = 1.0 if is_dup else 0.0

            # Track processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._processing_times.append(processing_time)
            if len(self._processing_times) > self._max_history:
                self._processing_times.pop(0)

            logger.debug(
                f"Hash comparison: {is_dup} "
                f"(score: {self._last_similarity_score}, "
                f"time: {processing_time:.2f}ms)"
            )

            return is_dup

        except Exception as e:
            logger.error(f"Hash comparison failed: {e}")
            raise DeduplicationError(f"Hash comparison failed: {e}")

    def get_similarity_score(self) -> float:
        """Get similarity score from last comparison.

        Returns:
            1.0 if images were identical, 0.0 if different
        """
        return self._last_similarity_score

    @property
    def name(self) -> str:
        """Strategy name."""
        return "hash"

    @property
    def avg_processing_time_ms(self) -> float:
        """Average processing time in milliseconds.

        Returns:
            Average processing time, or 0.0 if no comparisons yet
        """
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    def _compute_hash(self, image) -> str:
        """Compute hash of image data.

        Args:
            image: PIL Image object

        Returns:
            Hex digest of image hash
        """
        # Convert image to bytes
        image_bytes = image.tobytes()

        # Compute hash
        if self._hash_algorithm == 'md5':
            hash_obj = hashlib.md5(image_bytes)
        else:  # sha256
            hash_obj = hashlib.sha256(image_bytes)

        return hash_obj.hexdigest()

    def get_statistics(self) -> Dict[str, Any]:
        """Get strategy statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "name": self.name,
            "algorithm": self._hash_algorithm,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "comparisons_count": len(self._processing_times),
            "last_similarity_score": self._last_similarity_score,
        }
