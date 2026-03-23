#!/usr/bin/env python3
"""Region Profiler Analyzer Tool

Analyzes a sequence of frames to detect static slide regions vs dynamic
video/webcam regions. Useful for testing and tuning the adaptive deduplication.

Usage:
    python tools/region_analyzer.py <frames_dir> [options]
    python tools/region_analyzer.py <video_file> [options]

Examples:
    # Analyze frames in a directory
    python tools/region_analyzer.py ./captures/frames/

    # Analyze a video file (extracts frames automatically)
    python tools/region_analyzer.py recording.mp4

    # With visualization output
    python tools/region_analyzer.py ./frames/ --visual --output-dir ./analysis

    # Custom thresholds
    python tools/region_analyzer.py ./frames/ --change-threshold 30 --max-change-ratio 0.15
"""

import sys
import os
import argparse
import time
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Try to import cv2
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("Warning: OpenCV (cv2) not available. Video file support disabled.")


@dataclass
class RegionResult:
    """Result of region detection."""
    x: int
    y: int
    width: int
    height: int
    area: int
    area_ratio: float  # Percentage of screen


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    input_path: str
    frame_count: int
    frame_size: Tuple[int, int]
    static_regions: List[RegionResult]
    dynamic_coverage: float  # Percentage of screen that's dynamic
    static_coverage: float   # Percentage of screen that's static (in regions)
    confidence: float
    config: Dict[str, Any]
    processing_time_ms: float


class RegionAnalyzer:
    """Analyzes frame sequences to detect static vs dynamic regions."""

    def __init__(
        self,
        change_threshold: int = 25,
        max_change_ratio: float = 0.1,
        min_region_ratio: float = 0.1,
        max_regions: int = 5
    ):
        """
        Args:
            change_threshold: Pixel difference threshold (0-255)
            max_change_ratio: Max allowed change ratio for static pixels (0.0-1.0)
            min_region_ratio: Minimum region size as ratio of screen
            max_regions: Maximum number of regions to detect
        """
        self.change_threshold = change_threshold
        self.max_change_ratio = max_change_ratio
        self.min_region_ratio = min_region_ratio
        self.max_regions = max_regions

    def analyze_frames(self, frames: List[Image.Image]) -> Tuple[List[RegionResult], np.ndarray, float]:
        """Analyze frames to detect static regions.

        Args:
            frames: List of PIL Images

        Returns:
            Tuple of (regions, change_frequency_map, confidence)
        """
        if len(frames) < 2:
            raise ValueError("Need at least 2 frames for analysis")

        # Convert to grayscale numpy arrays
        np_frames = [np.array(frame.convert('L')) for frame in frames]
        h, w = np_frames[0].shape

        # Build change frequency map
        change_freq = np.zeros((h, w), dtype=np.float32)
        num_pairs = len(np_frames) - 1

        for i in range(num_pairs):
            if HAS_CV2:
                diff = cv2.absdiff(np_frames[i], np_frames[i+1])
            else:
                diff = np.abs(np_frames[i].astype(np.int16) - np_frames[i+1].astype(np.int16)).astype(np.uint8)

            binary_diff = (diff > self.change_threshold).astype(np.float32)
            change_freq += binary_diff

        # Normalize to 0-1 range (frequency of change)
        change_freq_normalized = change_freq / num_pairs

        # Identify static pixels
        max_allowed_changes = max(1, int(num_pairs * self.max_change_ratio))
        static_mask = (change_freq <= max_allowed_changes).astype(np.uint8) * 255

        # Find largest rectangles
        rectangles = self._find_max_rectangles(static_mask, self.max_regions)

        # Filter by minimum size
        screen_area = h * w
        min_area = screen_area * self.min_region_ratio

        regions = []
        for x, y, rw, rh in rectangles:
            area = rw * rh
            if area >= min_area:
                regions.append(RegionResult(
                    x=x, y=y, width=rw, height=rh,
                    area=area,
                    area_ratio=area / screen_area
                ))

        # Calculate confidence
        confidence = self._calculate_confidence(regions, screen_area)

        return regions, change_freq_normalized, confidence

    def _find_max_rectangles(
        self,
        mask: np.ndarray,
        max_count: int = 5
    ) -> List[Tuple[int, int, int, int]]:
        """Find multiple non-overlapping rectangles in binary mask."""
        rectangles = []
        working_mask = mask.copy()

        for _ in range(max_count):
            rect = self._find_max_rectangle(working_mask)
            x, y, w, h = rect

            if w * h == 0:
                break

            rectangles.append(rect)
            working_mask[y:y+h, x:x+w] = 0

        return rectangles

    def _find_max_rectangle(self, mask: np.ndarray) -> Tuple[int, int, int, int]:
        """Find the largest rectangle of 255s using histogram algorithm."""
        h, w = mask.shape
        heights = np.zeros(w, dtype=np.int32)
        max_area = 0
        best_rect = (0, 0, 0, 0)

        for r in range(h):
            row = mask[r]
            heights[row == 255] += 1
            heights[row == 0] = 0

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

    def _calculate_confidence(self, regions: List[RegionResult], screen_area: int) -> float:
        """Calculate confidence score."""
        if not regions:
            return 0.0

        total_region_area = sum(r.area for r in regions)
        coverage_ratio = total_region_area / screen_area

        if 0.5 <= coverage_ratio <= 0.8:
            coverage_score = 1.0
        elif coverage_ratio < 0.5:
            coverage_score = coverage_ratio / 0.5
        else:
            coverage_score = max(0.0, 1.0 - (coverage_ratio - 0.8) / 0.2)

        region_count_score = 1.0 if len(regions) <= 2 else 0.7
        return min(1.0, max(0.0, coverage_score * region_count_score))


def load_frames_from_directory(dir_path: Path, max_frames: int = 100) -> List[Image.Image]:
    """Load frames from a directory of images."""
    extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    files = sorted([
        f for f in dir_path.iterdir()
        if f.suffix.lower() in extensions
    ])

    if not files:
        raise ValueError(f"No image files found in {dir_path}")

    # Sample frames if too many
    if len(files) > max_frames:
        step = len(files) // max_frames
        files = files[::step][:max_frames]

    frames = []
    for f in files:
        try:
            img = Image.open(f)
            frames.append(img.copy())
            img.close()
        except Exception as e:
            print(f"Warning: Could not load {f}: {e}")

    return frames


def load_frames_from_video(video_path: Path, max_frames: int = 100, fps: float = 10) -> List[Image.Image]:
    """Extract frames from a video file."""
    if not HAS_CV2:
        raise RuntimeError("OpenCV required for video file support. Install with: pip install opencv-python")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Calculate frame sampling interval
    frame_interval = max(1, int(video_fps / fps))

    frames = []
    frame_idx = 0

    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb_frame))

        frame_idx += 1

    cap.release()
    return frames


def create_visualization(
    frames: List[Image.Image],
    regions: List[RegionResult],
    change_freq: np.ndarray,
    output_path: Path
):
    """Create visualization showing detected regions and change frequency."""
    # Use first frame as base
    base = frames[0].convert('RGB')
    w, h = base.size

    # Create 2x2 grid
    grid_w, grid_h = w * 2, h * 2
    grid = Image.new('RGB', (grid_w, grid_h), (30, 30, 40))

    # 1. Original frame (top-left)
    grid.paste(base, (0, 0))

    # 2. Change frequency heatmap (top-right)
    heatmap = create_heatmap(change_freq)
    heatmap_rgb = Image.fromarray(heatmap).resize((w, h))
    grid.paste(heatmap_rgb, (w, 0))

    # 3. Static mask visualization (bottom-left)
    static_viz = base.copy()
    draw = ImageDraw.Draw(static_viz, 'RGBA')

    # Draw detected static regions in green
    for i, region in enumerate(regions):
        color = (16, 185, 129, 100)  # Emerald green, semi-transparent
        draw.rectangle(
            [region.x, region.y, region.x + region.width, region.y + region.height],
            fill=color,
            outline=(16, 185, 129, 255),
            width=3
        )
        # Label
        label = f"R{i+1}: {region.area_ratio*100:.1f}%"
        draw.text((region.x + 5, region.y + 5), label, fill=(255, 255, 255))

    grid.paste(static_viz, (0, h))

    # 4. Dynamic regions highlighted (bottom-right)
    dynamic_viz = base.copy()
    draw_dyn = ImageDraw.Draw(dynamic_viz, 'RGBA')

    # Highlight dynamic areas in red
    dynamic_mask = (change_freq > 0.3).astype(np.uint8) * 255
    if HAS_CV2:
        contours, _ = cv2.findContours(dynamic_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if cv2.contourArea(contour) > 1000:  # Minimum area
                x, y, cw, ch = cv2.boundingRect(contour)
                draw_dyn.rectangle(
                    [x, y, x + cw, y + ch],
                    fill=(239, 68, 68, 80),  # Red, semi-transparent
                    outline=(239, 68, 68, 255),
                    width=2
                )

    grid.paste(dynamic_viz, (w, h))

    # Add labels
    draw_grid = ImageDraw.Draw(grid)
    labels = [
        (10, 10, "Original Frame"),
        (w + 10, 10, "Change Frequency (Yellow=Dynamic)"),
        (10, h + 10, "Static Regions (Green)"),
        (w + 10, h + 10, "Dynamic Regions (Red)")
    ]
    for x, y, text in labels:
        # Draw text with background
        draw_grid.rectangle([x-2, y-2, x + len(text)*8, y + 16], fill=(0, 0, 0, 180))
        draw_grid.text((x, y), text, fill=(255, 255, 255))

    grid.save(output_path)
    return output_path


def create_heatmap(change_freq: np.ndarray) -> np.ndarray:
    """Create a heatmap from change frequency map."""
    # Normalize to 0-255
    normalized = (change_freq * 255).astype(np.uint8)

    # Create RGB heatmap (blue=static, yellow/red=dynamic)
    h, w = normalized.shape
    heatmap = np.zeros((h, w, 3), dtype=np.uint8)

    # Blue channel: inverse of change (static areas)
    heatmap[:, :, 2] = 255 - normalized

    # Red channel: change frequency
    heatmap[:, :, 0] = normalized

    # Green channel: medium change
    heatmap[:, :, 1] = np.clip(normalized * 0.7, 0, 255).astype(np.uint8)

    return heatmap


def print_report(result: AnalysisResult):
    """Print analysis report to console."""
    print("\n" + "="*70)
    print("REGION PROFILER ANALYSIS REPORT")
    print("="*70)

    print(f"\nInput: {result.input_path}")
    print(f"Frames analyzed: {result.frame_count}")
    print(f"Frame size: {result.frame_size[0]}x{result.frame_size[1]}")
    print(f"Processing time: {result.processing_time_ms:.1f}ms")

    print("\n" + "-"*70)
    print("CONFIGURATION")
    print("-"*70)
    for key, value in result.config.items():
        print(f"  {key}: {value}")

    print("\n" + "-"*70)
    print("DETECTED STATIC REGIONS")
    print("-"*70)

    if result.static_regions:
        for i, region in enumerate(result.static_regions):
            print(f"\n  Region {i+1}:")
            print(f"    Position: ({region.x}, {region.y})")
            print(f"    Size: {region.width}x{region.height}")
            print(f"    Area: {region.area:,} pixels ({region.area_ratio*100:.1f}% of screen)")
    else:
        print("  No static regions detected (entire screen may be dynamic)")

    print("\n" + "-"*70)
    print("COVERAGE ANALYSIS")
    print("-"*70)
    print(f"  Static coverage: {result.static_coverage*100:.1f}%")
    print(f"  Dynamic coverage: {result.dynamic_coverage*100:.1f}%")
    print(f"  Confidence: {result.confidence:.2f}")

    print("\n" + "-"*70)
    print("INTERPRETATION")
    print("-"*70)

    if result.confidence >= 0.8:
        print("  HIGH CONFIDENCE - Clear separation between static and dynamic regions")
        print("  Adaptive deduplication should work well with these regions")
    elif result.confidence >= 0.5:
        print("  MEDIUM CONFIDENCE - Some static regions detected")
        print("  Adaptive deduplication may help but consider adjusting thresholds")
    else:
        print("  LOW CONFIDENCE - Difficult to identify static regions")
        print("  Consider using perceptual hashing instead of region-based approach")

    if result.static_coverage < 0.3:
        print("\n  WARNING: Very low static coverage. The content may be:")
        print("    - A full-screen video")
        print("    - Highly animated presentation")
        print("    - Screen with constant motion")

    if result.static_coverage > 0.9:
        print("\n  NOTE: Very high static coverage. The content may be:")
        print("    - A static document/presentation")
        print("    - Consider using hash-based deduplication instead")

    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze frames to detect static vs dynamic regions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('input', help='Directory of frames or video file')
    parser.add_argument('--output-dir', '-o', default='/tmp/region_analysis',
                       help='Output directory for reports')
    parser.add_argument('--visual', '-v', action='store_true',
                       help='Generate visual report')
    parser.add_argument('--json', '-j', action='store_true',
                       help='Generate JSON report')
    parser.add_argument('--max-frames', type=int, default=50,
                       help='Maximum frames to analyze (default: 50)')
    parser.add_argument('--change-threshold', type=int, default=25,
                       help='Pixel change threshold 0-255 (default: 25)')
    parser.add_argument('--max-change-ratio', type=float, default=0.1,
                       help='Max change ratio for static pixels (default: 0.1)')
    parser.add_argument('--min-region-ratio', type=float, default=0.1,
                       help='Minimum region size ratio (default: 0.1)')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Suppress console output')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load frames
    if not args.quiet:
        print(f"Loading frames from: {input_path}")

    start_time = time.time()

    if input_path.is_dir():
        frames = load_frames_from_directory(input_path, args.max_frames)
    elif input_path.is_file():
        frames = load_frames_from_video(input_path, args.max_frames)
    else:
        print(f"Error: {input_path} is not a valid file or directory")
        sys.exit(1)

    if len(frames) < 2:
        print("Error: Need at least 2 frames for analysis")
        sys.exit(1)

    if not args.quiet:
        print(f"Loaded {len(frames)} frames")
        print("Analyzing regions...")

    # Create analyzer and run
    analyzer = RegionAnalyzer(
        change_threshold=args.change_threshold,
        max_change_ratio=args.max_change_ratio,
        min_region_ratio=args.min_region_ratio
    )

    regions, change_freq, confidence = analyzer.analyze_frames(frames)

    processing_time = (time.time() - start_time) * 1000

    # Calculate coverage
    screen_area = frames[0].width * frames[0].height
    static_coverage = sum(r.area for r in regions) / screen_area if regions else 0
    dynamic_coverage = 1.0 - static_coverage

    # Build result
    result = AnalysisResult(
        input_path=str(input_path),
        frame_count=len(frames),
        frame_size=(frames[0].width, frames[0].height),
        static_regions=regions,
        static_coverage=static_coverage,
        dynamic_coverage=dynamic_coverage,
        confidence=confidence,
        config={
            'change_threshold': args.change_threshold,
            'max_change_ratio': args.max_change_ratio,
            'min_region_ratio': args.min_region_ratio,
            'max_frames': args.max_frames
        },
        processing_time_ms=processing_time
    )

    # Print report
    if not args.quiet:
        print_report(result)

    # Generate visual report
    if args.visual:
        visual_path = output_dir / f"region_analysis_{int(time.time())}.png"
        create_visualization(frames, regions, change_freq, visual_path)
        print(f"\nVisual report saved: {visual_path}")

    # Generate JSON report
    if args.json:
        json_path = output_dir / f"region_analysis_{int(time.time())}.json"

        # Helper to convert numpy types to Python native types
        def to_native(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            elif isinstance(obj, (np.floating,)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: to_native(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [to_native(x) for x in obj]
            return obj

        # Convert to JSON-serializable format
        json_data = to_native({
            'input_path': result.input_path,
            'frame_count': result.frame_count,
            'frame_size': result.frame_size,
            'static_regions': [asdict(r) for r in result.static_regions],
            'static_coverage': result.static_coverage,
            'dynamic_coverage': result.dynamic_coverage,
            'confidence': result.confidence,
            'config': result.config,
            'processing_time_ms': result.processing_time_ms
        })

        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        print(f"JSON report saved: {json_path}")


if __name__ == '__main__':
    main()
