"""Region profiler for adaptive deduplication.

This module periodically samples screenshots to detect static slide regions,
allowing deduplication to ignore dynamic video/webcam areas.
"""

import logging
import time
import asyncio
from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class RegionProfile:
    """Profile containing detected static regions.

    Attributes:
        regions: List of (x, y, w, h) rectangles for static regions
        created_at: Unix timestamp when profile was created
        expires_at: Unix timestamp when profile expires
        screen_size: (width, height) of the screen
        confidence: Confidence score 0.0-1.0 (higher = more stable regions)
    """
    regions: List[Tuple[int, int, int, int]]  # [(x, y, w, h), ...]
    created_at: float
    expires_at: float
    screen_size: Tuple[int, int]  # (width, height)
    confidence: float

    def is_valid(self) -> bool:
        """Check if profile is still valid (not expired)."""
        return time.time() < self.expires_at

    def total_area_ratio(self) -> float:
        """Calculate what percentage of screen is covered by regions."""
        if not self.regions:
            return 0.0
        total_area = sum(w * h for x, y, w, h in self.regions)
        screen_area = self.screen_size[0] * self.screen_size[1]
        return total_area / screen_area if screen_area > 0 else 0.0


class RegionProfiler:
    """Periodically detects static slide regions for adaptive deduplication.

    This class samples screenshots at regular intervals to identify which parts
    of the screen contain static content (slides) vs dynamic content (video/webcam).
    """

    def __init__(self, config: dict):
        """Initialize region profiler.

        Args:
            config: Configuration dictionary with:
                - sampling_interval: Seconds between region re-detections (default: 30)
                - sample_count: Number of screenshots per sampling (default: 20)
                - sample_freq: Samples per second during sampling (default: 10)
                - min_region_ratio: Minimum region size as ratio of screen (default: 0.5)
                - max_regions: Maximum number of regions to detect (default: 2)
                - change_threshold: Pixel difference threshold (default: 25)
                - max_change_ratio: Max allowed change ratio for static pixels (default: 0.1)
        """
        self.sampling_interval = config.get('sampling_interval', 30)
        self.sample_count = config.get('sample_count', 20)
        self.sample_freq = config.get('sample_freq', 10)
        self.min_region_ratio = config.get('min_region_ratio', 0.5)
        self.max_regions = config.get('max_regions', 2)
        self.change_threshold = config.get('change_threshold', 25)
        self.max_change_ratio = config.get('max_change_ratio', 0.1)

        logger.info(
            f"RegionProfiler initialized: interval={self.sampling_interval}s, "
            f"samples={self.sample_count}, freq={self.sample_freq}fps"
        )

    async def sample_and_detect(self, capture_provider) -> RegionProfile:
        """Capture samples and detect static regions.

        Args:
            capture_provider: Capture provider to get screenshots from

        Returns:
            RegionProfile with detected regions and confidence score
        """
        logger.info(f"Starting region sampling ({self.sample_count} frames @ {self.sample_freq}fps)...")

        # 1. Capture sample screenshots
        frames = await self._capture_samples(capture_provider)

        if len(frames) < 2:
            logger.warning("Insufficient frames captured for region detection")
            return self._create_fallback_profile(frames[0] if frames else None)

        # 2. Detect static regions using motion analysis
        static_regions = self._detect_static_regions(frames)

        # 3. Filter and rank regions by area
        screen_area = frames[0].width * frames[0].height
        valid_regions = self._filter_regions(static_regions, screen_area)

        # 4. Calculate confidence based on region stability
        confidence = self._calculate_confidence(frames, valid_regions)

        # 5. Create and return profile
        now = time.time()
        profile = RegionProfile(
            regions=valid_regions[:self.max_regions],
            created_at=now,
            expires_at=now + self.sampling_interval,
            screen_size=(frames[0].width, frames[0].height),
            confidence=confidence
        )

        logger.info(
            f"Region detection complete: {len(profile.regions)} regions, "
            f"coverage={profile.total_area_ratio()*100:.1f}%, "
            f"confidence={confidence:.2f}"
        )

        return profile

    async def _capture_samples(self, capture_provider) -> List[Image.Image]:
        """Capture sample screenshots at configured frequency.

        Args:
            capture_provider: Capture provider to get screenshots from

        Returns:
            List of PIL Images
        """
        frames = []
        interval = 1.0 / self.sample_freq  # Time between captures

        for i in range(self.sample_count):
            try:
                # Capture screenshot
                capture = capture_provider.capture()
                if capture and capture.image:
                    frames.append(capture.image)
                else:
                    logger.warning(f"Failed to capture frame {i+1}/{self.sample_count}")

                # Wait for next sample (except on last iteration)
                if i < self.sample_count - 1:
                    await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error capturing sample {i+1}: {e}")

        logger.debug(f"Captured {len(frames)} frames for analysis")
        return frames

    def _detect_static_regions(self, frames: List[Image.Image]) -> List[Tuple[int, int, int, int]]:
        """Detect static regions using change frequency analysis.

        Algorithm (from detect_video_region.py in 'static' mode):
        1. Convert frames to grayscale numpy arrays
        2. Compute pixel-wise differences between consecutive frames
        3. Accumulate changes into frequency map
        4. Threshold: pixels that changed <= max_change_ratio of time
        5. Find largest rectangles in stable pixel mask
        6. Return sorted by area (largest first)

        Args:
            frames: List of PIL Images

        Returns:
            List of (x, y, w, h) rectangles sorted by area (largest first)
        """
        if len(frames) < 2:
            return []

        # 1. Convert to numpy arrays (grayscale)
        np_frames = [np.array(frame.convert('L')) for frame in frames]
        h, w = np_frames[0].shape

        # 2. Build change frequency map
        change_freq = np.zeros((h, w), dtype=np.float32)
        num_pairs = len(np_frames) - 1

        for i in range(num_pairs):
            diff = cv2.absdiff(np_frames[i], np_frames[i+1])
            _, binary_diff = cv2.threshold(diff, self.change_threshold, 1, cv2.THRESH_BINARY)
            change_freq += binary_diff.astype(np.float32)

        # 3. Identify static pixels (changed in <= max_change_ratio of frames)
        max_allowed_changes = max(1, int(num_pairs * self.max_change_ratio))
        _, static_mask = cv2.threshold(
            change_freq,
            max_allowed_changes,
            255,
            cv2.THRESH_BINARY_INV
        )
        static_mask = static_mask.astype(np.uint8)

        logger.debug(
            f"Static pixel detection: {np.sum(static_mask == 255)} pixels stable "
            f"(max {max_allowed_changes}/{num_pairs} changes allowed)"
        )

        # 4. Find largest rectangles in static mask
        rectangles = self._find_max_rectangles(static_mask, max_count=5)

        return rectangles

    def _find_max_rectangles(
        self,
        mask: np.ndarray,
        max_count: int = 5
    ) -> List[Tuple[int, int, int, int]]:
        """Find multiple non-overlapping rectangles in binary mask.

        Strategy:
        1. Find largest rectangle
        2. Mask it out (set to 0)
        3. Find next largest
        4. Repeat up to max_count times

        Args:
            mask: Binary mask (255 = static, 0 = dynamic)
            max_count: Maximum number of rectangles to find

        Returns:
            List of (x, y, w, h) rectangles sorted by area
        """
        rectangles = []
        working_mask = mask.copy()

        for _ in range(max_count):
            rect = self._find_max_rectangle(working_mask)
            x, y, w, h = rect

            if w * h == 0:  # No more rectangles
                break

            rectangles.append(rect)

            # Mask out this rectangle for next iteration
            working_mask[y:y+h, x:x+w] = 0

        return rectangles

    def _find_max_rectangle(self, mask: np.ndarray) -> Tuple[int, int, int, int]:
        """Find the largest rectangle of 255s in a binary mask.

        Uses histogram-based algorithm - O(n*m) complexity.
        Based on logic_hints/detect_video_region.py

        Args:
            mask: Binary mask (255 = target, 0 = background)

        Returns:
            Tuple (x, y, w, h) of largest rectangle
        """
        h, w = mask.shape
        heights = np.zeros(w, dtype=np.int32)
        max_area = 0
        best_rect = (0, 0, 0, 0)  # x, y, w, h

        for r in range(h):
            # Update histogram heights
            row = mask[r]
            heights[row == 255] += 1
            heights[row == 0] = 0

            # Find largest rectangle in current histogram
            stack = []
            h_row = np.append(heights, 0)

            for i, height in enumerate(h_row):
                start_index = i
                while stack and stack[-1][1] >= height:
                    idx, h_val = stack.pop()
                    area = h_val * (i - idx)
                    if area > max_area:
                        max_area = area
                        best_rect = (idx, r - h_val + 1, i - idx, h_val)
                    start_index = idx
                stack.append((start_index, height))

        return best_rect

    def _filter_regions(
        self,
        regions: List[Tuple[int, int, int, int]],
        screen_area: int
    ) -> List[Tuple[int, int, int, int]]:
        """Filter regions by minimum size threshold.

        Args:
            regions: List of (x, y, w, h) rectangles
            screen_area: Total screen area in pixels

        Returns:
            Filtered list sorted by area (largest first)
        """
        min_area = screen_area * self.min_region_ratio

        valid_regions = [
            (x, y, w, h) for x, y, w, h in regions
            if w * h >= min_area
        ]

        # Sort by area (largest first)
        valid_regions.sort(key=lambda r: r[2] * r[3], reverse=True)

        logger.debug(
            f"Region filtering: {len(valid_regions)}/{len(regions)} regions "
            f">= {self.min_region_ratio*100:.0f}% of screen"
        )

        return valid_regions

    def _calculate_confidence(
        self,
        frames: List[Image.Image],
        regions: List[Tuple[int, int, int, int]]
    ) -> float:
        """Calculate confidence score for detected regions.

        Confidence is based on:
        - Number of regions found (more = lower confidence in some cases)
        - Coverage ratio (closer to ideal 50-80% = higher confidence)
        - Stability of regions across frames

        Args:
            frames: List of frames analyzed
            regions: Detected regions

        Returns:
            Confidence score 0.0-1.0
        """
        if not regions or not frames:
            return 0.0

        # Base confidence from coverage ratio
        screen_area = frames[0].width * frames[0].height
        total_region_area = sum(w * h for x, y, w, h in regions)
        coverage_ratio = total_region_area / screen_area

        # Ideal coverage is 50-80% of screen
        if 0.5 <= coverage_ratio <= 0.8:
            coverage_score = 1.0
        elif coverage_ratio < 0.5:
            coverage_score = coverage_ratio / 0.5  # Scale 0-50% -> 0-1
        else:
            coverage_score = max(0.0, 1.0 - (coverage_ratio - 0.8) / 0.2)  # Scale 80-100% -> 1-0

        # Penalty for too many regions (suggests fragmentation)
        region_count_score = 1.0 if len(regions) <= 2 else 0.7

        # Combined confidence
        confidence = coverage_score * region_count_score

        return min(1.0, max(0.0, confidence))

    def _create_fallback_profile(self, sample_frame: Optional[Image.Image]) -> RegionProfile:
        """Create fallback profile when region detection fails.

        Args:
            sample_frame: Sample frame to get dimensions from (if available)

        Returns:
            RegionProfile with no regions (triggers fallback in strategy)
        """
        if sample_frame:
            screen_size = (sample_frame.width, sample_frame.height)
        else:
            screen_size = (1920, 1080)  # Default fallback

        now = time.time()
        return RegionProfile(
            regions=[],
            created_at=now,
            expires_at=now + self.sampling_interval,
            screen_size=screen_size,
            confidence=0.0
        )
