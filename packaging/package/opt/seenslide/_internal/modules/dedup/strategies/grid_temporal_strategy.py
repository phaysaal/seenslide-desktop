"""Grid-based Temporal Change Detection Strategy for Slide Deduplication.

This is a proof-of-concept implementation of a novel deduplication algorithm that:
1. Divides the screen into an X*Y grid of blocks
2. Tracks per-block change rates using perceptual hashing
3. Classifies blocks as: video (high change), static (low change), or info (medium change)
4. Uses only "info" blocks to determine slide uniqueness
5. Supports merging consecutive slides with minimal info-block changes

Author: SeenSlide Team
Date: January 2025
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple

import numpy as np
import imagehash
from PIL import Image

from core.interfaces.dedup import IDeduplicationStrategy, DeduplicationError
from core.models.slide import RawCapture

logger = logging.getLogger(__name__)


class BlockType(Enum):
    """Classification of a grid block based on its temporal change rate."""
    UNKNOWN = "unknown"      # Not yet classified (insufficient history)
    STATIC = "static"        # Rarely changes (backgrounds, borders)
    INFO = "info"            # Changes at moderate rate (slide content)
    VIDEO = "video"          # Rapidly changing (embedded video, animations)


@dataclass
class BlockState:
    """State tracking for a single grid block."""
    row: int
    col: int
    current_hash: Optional[imagehash.ImageHash] = None
    hash_history: deque = field(default_factory=lambda: deque(maxlen=20))
    change_history: deque = field(default_factory=lambda: deque(maxlen=20))
    block_type: BlockType = BlockType.UNKNOWN
    change_rate: float = 0.0
    last_significant_hash: Optional[imagehash.ImageHash] = None

    def update_classification(self, static_threshold: float, video_threshold: float):
        """Update block classification based on change history."""
        if len(self.change_history) < 3:
            self.block_type = BlockType.UNKNOWN
            return

        # Calculate change rate (fraction of frames where block changed)
        self.change_rate = sum(self.change_history) / len(self.change_history)

        if self.change_rate < static_threshold:
            self.block_type = BlockType.STATIC
        elif self.change_rate > video_threshold:
            self.block_type = BlockType.VIDEO
        else:
            self.block_type = BlockType.INFO


@dataclass
class GridState:
    """State of the entire grid."""
    rows: int
    cols: int
    blocks: List[List[BlockState]] = field(default_factory=list)
    frame_count: int = 0

    def __post_init__(self):
        """Initialize block states for all grid positions."""
        self.blocks = [
            [BlockState(row=r, col=c) for c in range(self.cols)]
            for r in range(self.rows)
        ]

    def get_info_blocks(self) -> List[BlockState]:
        """Get all blocks classified as INFO."""
        return [
            block
            for row in self.blocks
            for block in row
            if block.block_type == BlockType.INFO
        ]

    def get_block_type_counts(self) -> Dict[BlockType, int]:
        """Count blocks by type."""
        counts = {bt: 0 for bt in BlockType}
        for row in self.blocks:
            for block in row:
                counts[block.block_type] += 1
        return counts


class GridTemporalStrategy(IDeduplicationStrategy):
    """Grid-based temporal change detection for slide deduplication.

    This strategy implements a novel approach to slide deduplication:

    1. **Spatial Decomposition**: Divides the screen into a grid of blocks
    2. **Per-Block Hashing**: Computes perceptual hash for each block
    3. **Temporal Tracking**: Tracks change rate of each block over time
    4. **Block Classification**:
       - STATIC: Change rate < 0.1 (backgrounds, logos)
       - INFO: Change rate 0.1-0.7 (slide content, text, diagrams)
       - VIDEO: Change rate > 0.7 (embedded videos, animations)
    5. **Info-Focused Comparison**: Only INFO blocks determine uniqueness
    6. **Merge Support**: Small changes in INFO blocks can trigger merge

    This approach handles:
    - Embedded videos (ignored as VIDEO blocks)
    - Webcam overlays (detected as VIDEO and ignored)
    - Progressive reveals (detected as changes in INFO blocks)
    - Mouse cursors (usually in VIDEO or localized, filtered out)
    """

    def __init__(self):
        """Initialize the grid temporal strategy."""
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._last_similarity_score = 0.0
        self._processing_times: deque = deque(maxlen=100)

        # Grid configuration
        self._grid_rows = 8
        self._grid_cols = 12
        self._hash_size = 8

        # Classification thresholds
        self._static_threshold = 0.1   # Below this = STATIC
        self._video_threshold = 0.7    # Above this = VIDEO

        # Deduplication thresholds
        self._duplicate_threshold = 0.90  # INFO blocks similarity for duplicate
        self._merge_threshold = 0.95      # INFO blocks similarity for merge candidate
        self._min_info_blocks = 5         # Minimum INFO blocks required

        # State
        self._grid_state: Optional[GridState] = None
        self._last_capture: Optional[RawCapture] = None
        self._last_info_hashes: Dict[Tuple[int, int], imagehash.ImageHash] = {}

        # Statistics
        self._stats = {
            "frames_processed": 0,
            "unique_slides": 0,
            "duplicates": 0,
            "merge_candidates": 0,
            "video_blocks_detected": 0,
        }

    def initialize(self, config: dict) -> bool:
        """Initialize the strategy with configuration.

        Args:
            config: Configuration dictionary with optional keys:
                - grid_rows: int (default: 8)
                - grid_cols: int (default: 12)
                - hash_size: int (default: 8)
                - static_threshold: float (default: 0.1)
                - video_threshold: float (default: 0.7)
                - duplicate_threshold: float (default: 0.90)
                - merge_threshold: float (default: 0.95)
                - min_info_blocks: int (default: 5)

        Returns:
            True if initialization successful
        """
        try:
            self._config = config

            # Grid configuration
            self._grid_rows = config.get('grid_rows', 8)
            self._grid_cols = config.get('grid_cols', 12)
            self._hash_size = config.get('hash_size', 8)

            # Classification thresholds
            self._static_threshold = config.get('static_threshold', 0.1)
            self._video_threshold = config.get('video_threshold', 0.7)

            # Deduplication thresholds
            self._duplicate_threshold = config.get('duplicate_threshold', 0.90)
            self._merge_threshold = config.get('merge_threshold', 0.95)
            self._min_info_blocks = config.get('min_info_blocks', 5)

            # Initialize grid state
            self._grid_state = GridState(rows=self._grid_rows, cols=self._grid_cols)

            self._initialized = True
            logger.info(
                f"GridTemporalStrategy initialized: "
                f"grid={self._grid_rows}x{self._grid_cols}, "
                f"thresholds(static={self._static_threshold}, "
                f"video={self._video_threshold}, "
                f"duplicate={self._duplicate_threshold})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize GridTemporalStrategy: {e}")
            return False

    def _extract_block(self, image: Image.Image, row: int, col: int) -> Image.Image:
        """Extract a single block from the image.

        Args:
            image: Full image
            row: Block row index
            col: Block column index

        Returns:
            Cropped block image
        """
        width, height = image.size
        block_width = width // self._grid_cols
        block_height = height // self._grid_rows

        x1 = col * block_width
        y1 = row * block_height
        x2 = x1 + block_width
        y2 = y1 + block_height

        # Handle edge blocks (may be slightly larger due to rounding)
        if col == self._grid_cols - 1:
            x2 = width
        if row == self._grid_rows - 1:
            y2 = height

        return image.crop((x1, y1, x2, y2))

    def _compute_block_hash(self, block_image: Image.Image) -> imagehash.ImageHash:
        """Compute perceptual hash for a block.

        Args:
            block_image: Block image

        Returns:
            Perceptual hash
        """
        return imagehash.phash(block_image, hash_size=self._hash_size)

    def _hash_similarity(self, hash1: imagehash.ImageHash,
                         hash2: imagehash.ImageHash) -> float:
        """Compute similarity between two hashes.

        Args:
            hash1: First hash
            hash2: Second hash

        Returns:
            Similarity score 0.0-1.0
        """
        max_distance = self._hash_size * self._hash_size
        hamming_distance = hash1 - hash2
        return 1.0 - (hamming_distance / max_distance)

    def _update_grid_state(self, image: Image.Image):
        """Update grid state with new image.

        Computes hashes for all blocks and updates change history.

        Args:
            image: New captured image
        """
        for row in range(self._grid_rows):
            for col in range(self._grid_cols):
                block = self._grid_state.blocks[row][col]
                block_image = self._extract_block(image, row, col)
                new_hash = self._compute_block_hash(block_image)

                # Track change from previous frame
                if block.current_hash is not None:
                    similarity = self._hash_similarity(new_hash, block.current_hash)
                    changed = similarity < 0.95  # Block changed if similarity < 95%
                    block.change_history.append(1.0 if changed else 0.0)

                # Update hash
                block.hash_history.append(new_hash)
                block.current_hash = new_hash

                # Update classification
                block.update_classification(
                    self._static_threshold,
                    self._video_threshold
                )

        self._grid_state.frame_count += 1

    def _compare_info_blocks(self, current_image: Image.Image,
                             previous_image: Image.Image) -> Tuple[float, Dict[str, Any]]:
        """Compare INFO blocks between two images.

        Args:
            current_image: Current capture image
            previous_image: Previous capture image

        Returns:
            Tuple of (similarity_score, details_dict)
        """
        info_blocks = self._grid_state.get_info_blocks()

        if len(info_blocks) < self._min_info_blocks:
            # Not enough INFO blocks - fall back to full comparison
            logger.warning(
                f"Only {len(info_blocks)} INFO blocks (need {self._min_info_blocks}). "
                f"Using full image comparison."
            )
            current_hash = imagehash.phash(current_image, hash_size=self._hash_size)
            previous_hash = imagehash.phash(previous_image, hash_size=self._hash_size)
            similarity = self._hash_similarity(current_hash, previous_hash)
            return similarity, {"mode": "full_image", "info_block_count": len(info_blocks)}

        # Compare each INFO block
        similarities = []
        changed_blocks = []

        for block in info_blocks:
            current_block = self._extract_block(current_image, block.row, block.col)
            previous_block = self._extract_block(previous_image, block.row, block.col)

            current_hash = self._compute_block_hash(current_block)
            previous_hash = self._compute_block_hash(previous_block)

            sim = self._hash_similarity(current_hash, previous_hash)
            similarities.append(sim)

            if sim < 0.9:  # Block significantly changed
                changed_blocks.append({
                    "row": block.row,
                    "col": block.col,
                    "similarity": sim,
                    "change_rate": block.change_rate
                })

        # Overall similarity is average of INFO block similarities
        overall_similarity = np.mean(similarities) if similarities else 0.0

        details = {
            "mode": "info_blocks",
            "info_block_count": len(info_blocks),
            "changed_block_count": len(changed_blocks),
            "changed_blocks": changed_blocks[:5],  # Limit for logging
            "min_similarity": min(similarities) if similarities else 0.0,
            "max_similarity": max(similarities) if similarities else 0.0,
        }

        return overall_similarity, details

    def is_duplicate(self, current: RawCapture, previous: RawCapture,
                     crop_region: Optional[Dict[str, int]] = None) -> bool:
        """Check if current capture is duplicate of previous.

        This method:
        1. Updates grid state with current image
        2. Compares only INFO blocks between current and previous
        3. Returns True if INFO blocks are similar enough

        Args:
            current: Current capture
            previous: Previous capture
            crop_region: Optional crop region (not used in grid strategy)

        Returns:
            True if duplicate, False if unique
        """
        if not self._initialized:
            raise DeduplicationError("Strategy not initialized")

        try:
            start_time = time.time()

            current_img = current.image
            previous_img = previous.image

            # Update grid state with current image
            self._update_grid_state(current_img)
            self._stats["frames_processed"] += 1

            # Log grid classification
            type_counts = self._grid_state.get_block_type_counts()
            logger.info(f"  Grid Classification: {dict(type_counts)}")
            self._stats["video_blocks_detected"] = type_counts[BlockType.VIDEO]

            # Compare INFO blocks
            similarity, details = self._compare_info_blocks(current_img, previous_img)
            self._last_similarity_score = similarity

            logger.info(f"  INFO Block Comparison:")
            logger.info(f"    Mode: {details['mode']}")
            logger.info(f"    INFO blocks: {details['info_block_count']}")
            if details['mode'] == 'info_blocks':
                logger.info(f"    Changed blocks: {details['changed_block_count']}")
                logger.info(f"    Similarity range: {details['min_similarity']:.3f} - {details['max_similarity']:.3f}")
            logger.info(f"    Overall similarity: {similarity:.4f}")
            logger.info(f"    Duplicate threshold: {self._duplicate_threshold}")

            # Determine if duplicate
            is_dup = similarity >= self._duplicate_threshold

            # Check for merge candidate (very high similarity but not identical)
            is_merge_candidate = (
                self._merge_threshold <= similarity < 1.0 and
                details.get('changed_block_count', 0) <= 3
            )

            if is_merge_candidate:
                self._stats["merge_candidates"] += 1
                logger.info(f"    MERGE CANDIDATE: Only {details.get('changed_block_count', 0)} blocks changed")

            # Track processing time
            processing_time = (time.time() - start_time) * 1000
            self._processing_times.append(processing_time)

            if is_dup:
                self._stats["duplicates"] += 1
                logger.info(f"    Result: DUPLICATE (similarity {similarity:.4f} >= {self._duplicate_threshold})")
            else:
                self._stats["unique_slides"] += 1
                logger.info(f"    Result: UNIQUE (similarity {similarity:.4f} < {self._duplicate_threshold})")

            logger.info(f"    Processing time: {processing_time:.2f}ms")

            return is_dup

        except Exception as e:
            logger.error(f"Grid temporal comparison failed: {e}", exc_info=True)
            raise DeduplicationError(f"Grid temporal comparison failed: {e}")

    def get_similarity_score(self) -> float:
        """Get similarity score from last comparison."""
        return self._last_similarity_score

    @property
    def name(self) -> str:
        """Strategy name."""
        return "grid_temporal"

    @property
    def avg_processing_time_ms(self) -> float:
        """Average processing time in milliseconds."""
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics.

        Returns:
            Dictionary with statistics including:
            - Grid configuration
            - Block type distribution
            - Processing metrics
            - Deduplication results
        """
        type_counts = {}
        if self._grid_state:
            type_counts = {
                k.value: v
                for k, v in self._grid_state.get_block_type_counts().items()
            }

        return {
            "name": self.name,
            "config": {
                "grid_size": f"{self._grid_rows}x{self._grid_cols}",
                "total_blocks": self._grid_rows * self._grid_cols,
                "hash_size": self._hash_size,
                "static_threshold": self._static_threshold,
                "video_threshold": self._video_threshold,
                "duplicate_threshold": self._duplicate_threshold,
                "merge_threshold": self._merge_threshold,
            },
            "block_distribution": type_counts,
            "processing": {
                "avg_time_ms": self.avg_processing_time_ms,
                "frames_processed": self._stats["frames_processed"],
            },
            "results": {
                "unique_slides": self._stats["unique_slides"],
                "duplicates": self._stats["duplicates"],
                "merge_candidates": self._stats["merge_candidates"],
                "duplicate_rate": (
                    self._stats["duplicates"] / max(1, self._stats["frames_processed"])
                ),
            },
            "last_similarity_score": self._last_similarity_score,
        }

    def get_grid_visualization(self) -> Optional[np.ndarray]:
        """Get a visualization of the current grid classification.

        Returns:
            NumPy array (rows x cols) with block type codes:
            - 0: UNKNOWN
            - 1: STATIC
            - 2: INFO
            - 3: VIDEO
        """
        if not self._grid_state:
            return None

        type_to_code = {
            BlockType.UNKNOWN: 0,
            BlockType.STATIC: 1,
            BlockType.INFO: 2,
            BlockType.VIDEO: 3,
        }

        grid = np.zeros((self._grid_rows, self._grid_cols), dtype=np.int8)
        for row in range(self._grid_rows):
            for col in range(self._grid_cols):
                block = self._grid_state.blocks[row][col]
                grid[row, col] = type_to_code[block.block_type]

        return grid

    def get_change_rate_heatmap(self) -> Optional[np.ndarray]:
        """Get a heatmap of change rates across the grid.

        Returns:
            NumPy array (rows x cols) with change rates (0.0-1.0)
        """
        if not self._grid_state:
            return None

        heatmap = np.zeros((self._grid_rows, self._grid_cols), dtype=np.float32)
        for row in range(self._grid_rows):
            for col in range(self._grid_cols):
                block = self._grid_state.blocks[row][col]
                heatmap[row, col] = block.change_rate

        return heatmap
