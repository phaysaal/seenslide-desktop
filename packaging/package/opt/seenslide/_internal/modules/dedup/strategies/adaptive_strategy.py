"""Adaptive deduplication strategy using region profiling.

This strategy periodically detects static slide regions and only compares
those regions for deduplication, ignoring dynamic video/webcam areas.
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
from PIL import Image

import imagehash

from core.interfaces.dedup import IDeduplicationStrategy, DeduplicationError
from core.models.slide import RawCapture
from modules.dedup.region_profiler import RegionProfiler, RegionProfile

logger = logging.getLogger(__name__)


class AdaptiveDeduplicationStrategy(IDeduplicationStrategy):
    """Deduplication strategy that uses adaptive region profiling.

    This strategy automatically detects static slide regions by periodically
    sampling screenshots. It then compares only those regions for deduplication,
    effectively ignoring dynamic content like embedded videos or webcams.
    """

    def __init__(self, capture_provider=None):
        """Initialize adaptive deduplication strategy.

        Args:
            capture_provider: Capture provider for sampling screenshots
        """
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._last_similarity_score = 0.0
        self._processing_times = []
        self._max_history = 100

        self._threshold = 0.92  # Slightly lower to handle slide animations
        self._hash_size = 8

        self._capture_provider = capture_provider
        self._region_profiler: Optional[RegionProfiler] = None
        self._current_profile: Optional[RegionProfile] = None
        self._profiling_in_progress = False

    def initialize(self, config: dict) -> bool:
        """Initialize the strategy with configuration.

        Args:
            config: Dictionary containing strategy configuration:
                - dedup_threshold: float, 0.0-1.0 (default: 0.92)
                - perceptual_hash_size: int, hash size (default: 8)
                - adaptive: dict with region profiler config
                  - sampling_interval: seconds (default: 30)
                  - sample_count: number of samples (default: 20)
                  - sample_freq: samples per second (default: 10)
                  - min_region_ratio: minimum region size (default: 0.5)
                  - max_regions: max regions to track (default: 2)
                  - change_threshold: pixel diff threshold (default: 25)
                  - max_change_ratio: max change ratio for static (default: 0.1)

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            self._config = config
            self._threshold = config.get('dedup_threshold', 0.92)
            self._hash_size = config.get('perceptual_hash_size', 8)

            # Validate threshold
            if not 0.0 <= self._threshold <= 1.0:
                logger.error(f"Invalid threshold: {self._threshold}")
                return False

            # Validate hash size
            if self._hash_size not in [8, 16]:
                logger.error(f"Invalid hash size: {self._hash_size}")
                return False

            # Initialize region profiler
            adaptive_config = config.get('adaptive', {})
            self._region_profiler = RegionProfiler(adaptive_config)

            self._initialized = True
            logger.info(
                f"Adaptive deduplication strategy initialized "
                f"(threshold: {self._threshold}, hash_size: {self._hash_size})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize adaptive strategy: {e}")
            return False

    def set_capture_provider(self, capture_provider):
        """Set the capture provider for region profiling.

        Args:
            capture_provider: Capture provider instance
        """
        self._capture_provider = capture_provider
        logger.debug("Capture provider set for adaptive strategy")

    async def _ensure_valid_profile(self) -> bool:
        """Ensure we have a valid region profile.

        Returns:
            True if profile is valid or successfully refreshed, False otherwise
        """
        # Check if current profile is still valid
        if self._current_profile and self._current_profile.is_valid():
            return True

        # Check if profiling is already in progress
        if self._profiling_in_progress:
            logger.debug("Region profiling already in progress, waiting...")
            # Wait a bit and return False to skip this comparison
            return False

        # Need to create or refresh profile
        if not self._capture_provider:
            logger.warning("No capture provider available for region profiling")
            return False

        try:
            self._profiling_in_progress = True
            logger.info("Region profile expired or missing, resampling...")

            # Sample and detect regions
            self._current_profile = await self._region_profiler.sample_and_detect(
                self._capture_provider
            )

            if self._current_profile.regions:
                logger.info(
                    f"New region profile: {len(self._current_profile.regions)} regions, "
                    f"covering {self._current_profile.total_area_ratio()*100:.1f}% of screen, "
                    f"confidence: {self._current_profile.confidence:.2f}"
                )
            else:
                logger.warning(
                    "No static regions detected, will use full-screen comparison as fallback"
                )

            return True

        except Exception as e:
            logger.error(f"Failed to refresh region profile: {e}")
            return False

        finally:
            self._profiling_in_progress = False

    def is_duplicate(self, current: RawCapture, previous: RawCapture,
                     crop_region: Optional[Dict[str, int]] = None) -> bool:
        """Check if current is duplicate of previous using adaptive regions.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against
            crop_region: Ignored (adaptive strategy detects regions automatically)

        Returns:
            True if images are similar in detected regions, False otherwise

        Raises:
            DeduplicationError: If comparison fails
        """
        if not self._initialized:
            raise DeduplicationError("Strategy not initialized")

        try:
            start_time = time.time()

            # Ensure we have a valid region profile
            # Note: This is async, but we can't make is_duplicate async without
            # breaking the interface. We'll handle this by running the async
            # function in the current event loop or creating a new one.
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, we can't await here
                    # Fall back to full-screen comparison
                    if not self._current_profile or not self._current_profile.is_valid():
                        logger.warning(
                            "Region profile expired but can't refresh (event loop running). "
                            "Using full-screen comparison."
                        )
                        return self._compare_full_screen(current, previous)
                else:
                    # Event loop not running, we can run the async function
                    profile_valid = loop.run_until_complete(self._ensure_valid_profile())
                    if not profile_valid:
                        logger.warning("Failed to refresh profile, using full-screen comparison")
                        return self._compare_full_screen(current, previous)
            except RuntimeError:
                # No event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    profile_valid = loop.run_until_complete(self._ensure_valid_profile())
                    if not profile_valid:
                        logger.warning("Failed to refresh profile, using full-screen comparison")
                        return self._compare_full_screen(current, previous)
                finally:
                    loop.close()

            # Extract and compare regions
            if self._current_profile and self._current_profile.regions:
                # Region-based comparison
                current_regions = self._extract_regions(current.image, self._current_profile.regions)
                previous_regions = self._extract_regions(previous.image, self._current_profile.regions)

                similarity = self._compare_regions(current_regions, previous_regions)
            else:
                # Fallback to full-screen comparison
                logger.debug("No regions detected, using full-screen comparison")
                similarity = self._compare_images(current.image, previous.image)

            self._last_similarity_score = similarity
            is_dup = bool(similarity >= self._threshold)

            # Track processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._processing_times.append(processing_time)
            if len(self._processing_times) > self._max_history:
                self._processing_times.pop(0)

            logger.debug(
                f"Adaptive comparison: {is_dup} "
                f"(similarity: {similarity:.4f}, threshold: {self._threshold}, "
                f"regions: {len(self._current_profile.regions) if self._current_profile else 0}, "
                f"time: {processing_time:.2f}ms)"
            )

            return is_dup

        except Exception as e:
            logger.error(f"Adaptive comparison failed: {e}")
            raise DeduplicationError(f"Adaptive comparison failed: {e}")

    def _compare_full_screen(self, current: RawCapture, previous: RawCapture) -> bool:
        """Fallback to full-screen comparison.

        Args:
            current: Current capture
            previous: Previous capture

        Returns:
            True if duplicate, False otherwise
        """
        similarity = self._compare_images(current.image, previous.image)
        self._last_similarity_score = similarity
        return similarity >= self._threshold

    def _extract_regions(
        self,
        image: Image.Image,
        regions: List[tuple]
    ) -> List[Image.Image]:
        """Extract cropped regions from image.

        Args:
            image: Source image
            regions: List of (x, y, w, h) tuples

        Returns:
            List of cropped images
        """
        extracted = []
        for x, y, w, h in regions:
            try:
                region = image.crop((x, y, x + w, y + h))
                extracted.append(region)
            except Exception as e:
                logger.warning(f"Failed to extract region ({x}, {y}, {w}, {h}): {e}")
        return extracted

    def _compare_regions(
        self,
        current_regions: List[Image.Image],
        previous_regions: List[Image.Image]
    ) -> float:
        """Compare extracted regions using perceptual hashing.

        Returns average similarity across all regions.

        Args:
            current_regions: List of current region images
            previous_regions: List of previous region images

        Returns:
            Average similarity score 0.0-1.0
        """
        if len(current_regions) != len(previous_regions):
            logger.warning("Region count mismatch, returning 0 similarity")
            return 0.0

        if not current_regions:
            logger.warning("No regions to compare, returning 0 similarity")
            return 0.0

        similarities = []
        for i, (curr_img, prev_img) in enumerate(zip(current_regions, previous_regions)):
            try:
                similarity = self._compare_images(curr_img, prev_img)
                similarities.append(similarity)
                logger.debug(f"Region {i+1} similarity: {similarity:.4f}")
            except Exception as e:
                logger.warning(f"Failed to compare region {i+1}: {e}")

        # Return average similarity
        if similarities:
            return sum(similarities) / len(similarities)
        else:
            return 0.0

    def _compare_images(self, img1: Image.Image, img2: Image.Image) -> float:
        """Compare two images using perceptual hashing.

        Args:
            img1: First image
            img2: Second image

        Returns:
            Similarity score 0.0-1.0
        """
        # Compute perceptual hashes
        hash1 = imagehash.phash(img1, hash_size=self._hash_size)
        hash2 = imagehash.phash(img2, hash_size=self._hash_size)

        # Compute similarity
        max_distance = self._hash_size * self._hash_size
        hamming_distance = hash1 - hash2
        similarity = 1.0 - (hamming_distance / max_distance)

        return similarity

    def get_similarity_score(self) -> float:
        """Get similarity score from last comparison.

        Returns:
            Float 0.0-1.0 where 1.0 means identical, 0.0 means completely different
        """
        return self._last_similarity_score

    @property
    def name(self) -> str:
        """Strategy name."""
        return "adaptive"

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
        stats = {
            "name": self.name,
            "threshold": self._threshold,
            "hash_size": self._hash_size,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "comparisons_count": len(self._processing_times),
            "last_similarity_score": self._last_similarity_score,
        }

        if self._current_profile:
            stats["current_profile"] = {
                "regions_count": len(self._current_profile.regions),
                "coverage_ratio": self._current_profile.total_area_ratio(),
                "confidence": self._current_profile.confidence,
                "is_valid": self._current_profile.is_valid(),
                "expires_in_seconds": max(0, self._current_profile.expires_at - time.time())
            }
        else:
            stats["current_profile"] = None

        return stats
