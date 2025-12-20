"""Hybrid deduplication strategy combining multiple strategies."""

import logging
import time
from typing import Dict, Any, List

from core.interfaces.dedup import IDeduplicationStrategy, DeduplicationError
from core.models.slide import RawCapture
from modules.dedup.strategies.hash_strategy import HashDeduplicationStrategy
from modules.dedup.strategies.perceptual_strategy import PerceptualDeduplicationStrategy

logger = logging.getLogger(__name__)


class HybridDeduplicationStrategy(IDeduplicationStrategy):
    """Hybrid deduplication combining hash and perceptual strategies.

    This strategy uses a multi-stage approach:
    1. First tries exact hash matching (fast)
    2. If hashes differ, tries perceptual matching (slower but handles minor changes)

    This provides the best of both worlds: speed when slides are identical,
    and robustness when there are minor differences.
    """

    def __init__(self):
        """Initialize the hybrid deduplication strategy."""
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._last_similarity_score = 0.0
        self._processing_times = []
        self._max_history = 100

        # Strategy instances
        self._hash_strategy = HashDeduplicationStrategy()
        self._perceptual_strategy = PerceptualDeduplicationStrategy()

        # Statistics
        self._hash_matches = 0
        self._perceptual_matches = 0
        self._no_matches = 0

    def initialize(self, config: dict) -> bool:
        """Initialize the strategy with configuration.

        Args:
            config: Dictionary containing strategy configuration:
                - hash_algorithm: str, for hash strategy (default: 'md5')
                - perceptual_threshold: float, for perceptual (default: 0.95)
                - perceptual_hash_size: int, for perceptual (default: 8)
                - stages: list of strategy names (default: ['hash', 'perceptual'])

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config
            self._stages = config.get('stages', ['hash', 'perceptual'])

            # Validate stages
            valid_stages = {'hash', 'perceptual'}
            if not all(stage in valid_stages for stage in self._stages):
                logger.error(f"Invalid stages: {self._stages}")
                return False

            # Initialize sub-strategies
            if 'hash' in self._stages:
                if not self._hash_strategy.initialize(config):
                    logger.error("Failed to initialize hash strategy")
                    return False

            if 'perceptual' in self._stages:
                if not self._perceptual_strategy.initialize(config):
                    logger.error("Failed to initialize perceptual strategy")
                    return False

            self._initialized = True
            logger.info(
                f"Hybrid deduplication strategy initialized "
                f"with stages: {self._stages}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize hybrid strategy: {e}")
            return False

    def is_duplicate(self, current: RawCapture, previous: RawCapture) -> bool:
        """Check if current is duplicate using hybrid approach.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against

        Returns:
            True if images are duplicates, False otherwise

        Raises:
            DeduplicationError: If comparison fails
        """
        if not self._initialized:
            raise DeduplicationError("Strategy not initialized")

        try:
            start_time = time.time()
            is_dup = False
            matched_stage = None

            # Try each stage in order
            for stage in self._stages:
                if stage == 'hash':
                    is_dup = self._hash_strategy.is_duplicate(current, previous)
                    if is_dup:
                        matched_stage = 'hash'
                        self._hash_matches += 1
                        self._last_similarity_score = 1.0
                        break  # Exact match found, no need to check further

                elif stage == 'perceptual':
                    is_dup = self._perceptual_strategy.is_duplicate(current, previous)
                    if is_dup:
                        matched_stage = 'perceptual'
                        self._perceptual_matches += 1
                        self._last_similarity_score = (
                            self._perceptual_strategy.get_similarity_score()
                        )
                        break

            if not is_dup:
                self._no_matches += 1
                # Get similarity from last perceptual check if it ran
                if 'perceptual' in self._stages:
                    self._last_similarity_score = (
                        self._perceptual_strategy.get_similarity_score()
                    )
                else:
                    self._last_similarity_score = 0.0

            # Track processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._processing_times.append(processing_time)
            if len(self._processing_times) > self._max_history:
                self._processing_times.pop(0)

            logger.debug(
                f"Hybrid comparison: {is_dup} "
                f"(matched: {matched_stage}, "
                f"similarity: {self._last_similarity_score:.4f}, "
                f"time: {processing_time:.2f}ms)"
            )

            return is_dup

        except Exception as e:
            logger.error(f"Hybrid comparison failed: {e}")
            raise DeduplicationError(f"Hybrid comparison failed: {e}")

    def get_similarity_score(self) -> float:
        """Get similarity score from last comparison.

        Returns:
            Float 0.0-1.0 based on the matching strategy used
        """
        return self._last_similarity_score

    @property
    def name(self) -> str:
        """Strategy name."""
        return "hybrid"

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
        total_comparisons = (
            self._hash_matches + self._perceptual_matches + self._no_matches
        )

        return {
            "name": self.name,
            "stages": self._stages,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "comparisons_count": len(self._processing_times),
            "last_similarity_score": self._last_similarity_score,
            "hash_matches": self._hash_matches,
            "perceptual_matches": self._perceptual_matches,
            "no_matches": self._no_matches,
            "hash_match_rate": (
                self._hash_matches / total_comparisons
                if total_comparisons > 0 else 0.0
            ),
            "perceptual_match_rate": (
                self._perceptual_matches / total_comparisons
                if total_comparisons > 0 else 0.0
            ),
        }
