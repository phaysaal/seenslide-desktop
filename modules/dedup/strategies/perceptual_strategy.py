"""Perceptual deduplication strategy using image hashing."""

import logging
import time
from typing import Dict, Any, Optional

import imagehash
import numpy as np

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
            # Localized-change detection (catches a single revealed line that a
            # global perceptual hash averages away). The crop is downscaled to a
            # tile_px square grayscale thumbnail, split into a tile_grid × grid
            # of tiles; if any tile's mean abs brightness change exceeds
            # tile_tol, the frame is treated as a NEW slide even when the global
            # hash says "duplicate". Tuned so text changes trigger it but cursor
            # blink / compression noise do not.
            self._tile_px = config.get('perceptual_tile_px', 144)
            self._tile_grid = config.get('perceptual_tile_grid', 8)
            # Mean abs brightness change (0-255) a tile must exceed to count as a
            # real change. Measured noise floor (JPEG recompression) is ~0.5 and
            # a realistic single line of slide text scores ~7-20, so 4.0 catches
            # line-level changes with a wide margin over cursor/compression noise.
            self._tile_tol = config.get('perceptual_tile_tol', 4.0)

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

    def is_duplicate(self, current: RawCapture, previous: RawCapture,
                     crop_region: Optional[Dict[str, int]] = None) -> bool:
        """Check if current is duplicate of previous using perceptual hash.

        Args:
            current: Current capture to check
            previous: Previous capture to compare against
            crop_region: Optional region to crop before comparison.
                        Format: {"x": int, "y": int, "width": int, "height": int}
                        If None, compares full images (backward compatible)

        Returns:
            True if images are perceptually similar, False otherwise

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

            logger.info(f"  🔍 Perceptual Hash Comparison:")
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

            # Compute perceptual hashes.
            # dhash (gradient/difference hash) — numpy-only, no scipy. It's
            # robust for slide-change detection (structured, high-contrast
            # content) and drops a ~1GB scipy dependency that phash's DCT
            # would otherwise force into every packaged build. Hamming
            # distance and the hash_size^2 max below are identical to phash.
            logger.info(f"     Computing perceptual hashes (hash_size={self._hash_size}x{self._hash_size})...")
            current_hash = imagehash.dhash(current_img, hash_size=self._hash_size)
            previous_hash = imagehash.dhash(previous_img, hash_size=self._hash_size)

            logger.info(f"     Current hash:  {current_hash}")
            logger.info(f"     Previous hash: {previous_hash}")

            # Compute similarity
            # imagehash returns Hamming distance (0 = identical)
            # Convert to similarity score (0.0-1.0, where 1.0 = identical)
            max_distance = self._hash_size * self._hash_size
            hamming_distance = current_hash - previous_hash
            similarity = 1.0 - (hamming_distance / max_distance)

            logger.info(f"     Hamming distance: {hamming_distance} (out of {max_distance} bits)")
            logger.info(f"     Similarity score: {similarity:.6f} (1.0 = identical, 0.0 = completely different)")
            logger.info(f"     Threshold: {self._threshold}")

            self._last_similarity_score = similarity

            # Check if duplicate based on threshold
            is_dup = bool(similarity >= self._threshold)

            # Track processing time
            processing_time = (time.time() - start_time) * 1000  # ms
            self._processing_times.append(processing_time)
            if len(self._processing_times) > self._max_history:
                self._processing_times.pop(0)

            if is_dup:
                logger.info(f"     ✅ Images ARE similar (similarity {similarity:.6f} >= threshold {self._threshold})")
            else:
                logger.info(f"     ❌ Images are NOT similar (similarity {similarity:.6f} < threshold {self._threshold})")
            logger.info(f"     Processing time: {processing_time:.2f}ms")

            return is_dup

        except Exception as e:
            logger.error(f"❌ Perceptual comparison failed: {e}", exc_info=True)
            raise DeduplicationError(f"Perceptual comparison failed: {e}")

    def fingerprint(self, capture: RawCapture,
                    crop_region: Optional[Dict[str, int]] = None):
        """Compute the compact perceptual fingerprint (dhash) for a capture.

        Storing this instead of the full frame lets the dedup engine compare a
        new slide against the entire history using a few bytes per slide rather
        than holding every full-resolution image in memory.
        """
        img = capture.image
        if crop_region:
            x, y = crop_region['x'], crop_region['y']
            w, h = crop_region['width'], crop_region['height']
            img = img.crop((x, y, x + w, y + h))
        # Fingerprint = coarse global hash (fast whole-history compare) plus a
        # small grayscale thumbnail for localized-change detection. The thumb is
        # a few KB, so memory stays flat over a long talk.
        thumb = np.asarray(
            img.convert("L").resize((self._tile_px, self._tile_px)),
            dtype=np.uint8,
        )
        return {
            "dhash": imagehash.dhash(img, hash_size=self._hash_size),
            "thumb": thumb,
        }

    def compare_fingerprints(self, current_fp, previous_fp) -> bool:
        """Duplicate check from two precomputed fingerprints — no pixels.

        Two-stage: the global perceptual hash decides "clearly different"; if it
        says "duplicate", a tiled pixel-diff still promotes the frame to unique
        when a localized change (e.g. one revealed line) is present, which a
        global hash averages away. Updates the last similarity score.
        """
        cur_dh, prev_dh = current_fp["dhash"], previous_fp["dhash"]
        max_distance = self._hash_size * self._hash_size
        hamming_distance = cur_dh - prev_dh
        similarity = 1.0 - (hamming_distance / max_distance)
        self._last_similarity_score = similarity

        if similarity < self._threshold:
            return False  # globally different -> unique

        # Global hash says duplicate — check for a localized change it smoothed
        # over (incremental slide reveal). If found, treat as a new slide.
        if self._has_local_change(current_fp.get("thumb"), previous_fp.get("thumb")):
            # Report just-below-threshold so downstream logs read as "unique".
            self._last_similarity_score = min(similarity, self._threshold - 1e-6)
            return False
        return True

    def _has_local_change(self, a, b) -> bool:
        """True if any tile of the two thumbnails differs beyond tolerance.

        Splits the frames into a tile_grid × tile_grid grid and compares each
        tile's mean absolute brightness change. A single line of text lands in
        one or two tiles and drives their mean well past tile_tol, while cursor
        blink / JPEG noise stays a fraction of it. Fail-safe: any problem (shape
        mismatch, missing thumb) returns False so the global decision stands.
        """
        try:
            if a is None or b is None or a.shape != b.shape:
                return False
            diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
            n = a.shape[0]
            step = max(1, n // self._tile_grid)
            for i in range(0, n, step):
                for j in range(0, n, step):
                    tile = diff[i:i + step, j:j + step]
                    if tile.size and float(tile.mean()) > self._tile_tol:
                        return True
            return False
        except Exception:
            return False

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
