"""Perceptual deduplication strategy using image hashing."""

import logging
import time
from typing import Dict, Any

import imagehash

from core.interfaces.dedup import IDeduplicationStrategy, DeduplicationError
from core.models.slide import RawCapture

logger = logging.getLogger(__name__)


class PerceptualDeduplicationStrategy(IDeduplicationStrategy):
    """Perceptual deduplication using perceptual hashing.

    This strategy uses perceptual hashing (pHash) to compare images based on
    visual similarity rather than exact pixel matches. It can detect duplicates
    even when there are minor differences like cursor movement or small animations.
    """

    def __init__(self):
        """Initialize the perceptual deduplication strategy."""
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._last_similarity_score = 0.0
        self._processing_times = []
        self._max_history = 100
        self._threshold = 0.95

    def initialize(self, config: dict) -> bool:
        """Initialize the strategy with configuration.

        Args:
            config: Dictionary containing strategy configuration:
                - perceptual_threshold: float, 0.0-1.0 (default: 0.95)
                  Images with similarity >= threshold are considered duplicates
                - perceptual_hash_size: int, hash size (default: 8)
                  Larger = more precise but slower

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config
            self._threshold = config.get('perceptual_threshold', 0.95)
            self._hash_size = config.get('perceptual_hash_size', 8)

            # Validate threshold
            if not 0.0 <= self._threshold <= 1.0:
                logger.error(f"Invalid threshold: {self._threshold}")
                return False

            # Validate hash size
            if self._hash_size not in [8, 16]:
                logger.error(f"Invalid hash size: {self._hash_size}")
                return False

            self._initialized = True
            logger.info(
                f"Perceptual deduplication strategy initialized "
                f"(threshold: {self._threshold}, hash_size: {self._hash_size})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize perceptual strategy: {e}")
            return False

    def is_duplicate(self, current: RawCapture, previous: RawCapture) -> bool:
        """Check if current is duplicate of previous using perceptual hash.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against

        Returns:
            True if images are perceptually similar, False otherwise

        Raises:
            DeduplicationError: If comparison fails
        """
        if not self._initialized:
            raise DeduplicationError("Strategy not initialized")

        try:
            start_time = time.time()

            # Compute perceptual hashes
            current_hash = imagehash.phash(current.image, hash_size=self._hash_size)
            previous_hash = imagehash.phash(previous.image, hash_size=self._hash_size)

            # Compute similarity
            # imagehash returns Hamming distance (0 = identical)
            # Convert to similarity score (0.0-1.0, where 1.0 = identical)
            max_distance = self._hash_size * self._hash_size
            hamming_distance = current_hash - previous_hash
            similarity = 1.0 - (hamming_distance / max_distance)

            self._last_similarity_score = similarity

            # Check if duplicate based on threshold
            is_dup = bool(similarity >= self._threshold)

            # Track processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._processing_times.append(processing_time)
            if len(self._processing_times) > self._max_history:
                self._processing_times.pop(0)

            logger.debug(
                f"Perceptual comparison: {is_dup} "
                f"(similarity: {similarity:.4f}, threshold: {self._threshold}, "
                f"time: {processing_time:.2f}ms)"
            )

            return is_dup

        except Exception as e:
            logger.error(f"Perceptual comparison failed: {e}")
            raise DeduplicationError(f"Perceptual comparison failed: {e}")

    def get_similarity_score(self) -> float:
        """Get similarity score from last comparison.

        Returns:
            Float 0.0-1.0 where 1.0 means identical, 0.0 means completely different
        """
        return self._last_similarity_score

    @property
    def name(self) -> str:
        """Strategy name."""
        return "perceptual"

    @property
    def avg_processing_time_ms(self) -> float:
        """Average processing time in milliseconds.

        Returns:
            Average processing time, or 0.0 if no comparisons yet
        """
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    def get_statistics(self) -> Dict[str, Any]:
        """Get strategy statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "name": self.name,
            "threshold": self._threshold,
            "hash_size": self._hash_size,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "comparisons_count": len(self._processing_times),
            "last_similarity_score": self._last_similarity_score,
        }
