"""Hash-based deduplication strategy."""

import logging
import hashlib
import time
from typing import Dict, Any, Optional

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

    def is_duplicate(self, current: RawCapture, previous: RawCapture,
                     crop_region: Optional[Dict[str, int]] = None) -> bool:
        """Check if current is duplicate of previous using hash comparison.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against
            crop_region: Optional region to crop before comparison.
                        Format: {"x": int, "y": int, "width": int, "height": int}
                        If None, compares full images (backward compatible)

        Returns:
            True if images are identical (hashes match), False otherwise

        Raises:
            DeduplicationError: If comparison fails
        """
        if not self._initialized:
            raise DeduplicationError("Strategy not initialized")

        try:
            start_time = time.time()

            # Get images to compare
            current_img = current.image
            previous_img = previous.image

            logger.info(f"  🔍 Hash Comparison ({self._hash_algorithm.upper()}):")
            logger.info(f"     Original image size: {current_img.size}")

            # Crop if region specified
            if crop_region:
                x = crop_region['x']
                y = crop_region['y']
                w = crop_region['width']
                h = crop_region['height']

                # Crop both images to the specified region
                current_img = current_img.crop((x, y, x + w, y + h))
                previous_img = previous_img.crop((x, y, x + w, y + h))

                logger.info(f"     Cropped to: {current_img.size} (region: x={x}, y={y}, w={w}, h={h})")
            else:
                logger.info(f"     No cropping (comparing full images)")

            # Compute hashes
            logger.info(f"     Computing {self._hash_algorithm.upper()} hashes...")
            current_hash = self._compute_hash(current_img)
            previous_hash = self._compute_hash(previous_img)

            logger.info(f"     Current hash:  {current_hash[:16]}...{current_hash[-16:]}")
            logger.info(f"     Previous hash: {previous_hash[:16]}...{previous_hash[-16:]}")

            # Compare hashes
            is_dup = current_hash == previous_hash

            # Update similarity score (1.0 if identical, 0.0 if different)
            self._last_similarity_score = 1.0 if is_dup else 0.0

            # Track processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._processing_times.append(processing_time)
            if len(self._processing_times) > self._max_history:
                self._processing_times.pop(0)

            if is_dup:
                logger.info(f"     ✅ Hashes MATCH (images are pixel-perfect identical)")
            else:
                logger.info(f"     ❌ Hashes DIFFER (images have at least one pixel difference)")
            logger.info(f"     Processing time: {processing_time:.2f}ms")

            return is_dup

        except Exception as e:
            logger.error(f"❌ Hash comparison failed: {e}", exc_info=True)
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
