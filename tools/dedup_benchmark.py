#!/usr/bin/env python3
"""Deduplication Benchmark Tool

Compares multiple deduplication strategies on a sequence of frames,
providing side-by-side analysis and parameter tuning capabilities.

Usage:
    python tools/dedup_benchmark.py <frames_dir> [options]

Examples:
    # Basic comparison of all strategies
    python tools/dedup_benchmark.py ./captures/frames/

    # Compare with visual output
    python tools/dedup_benchmark.py ./frames/ --visual --output-dir ./benchmark

    # Parameter sweep for grid_temporal optimization
    python tools/dedup_benchmark.py ./frames/ --sweep grid_temporal

    # Compare specific strategies
    python tools/dedup_benchmark.py ./frames/ --strategies perceptual,grid_temporal

    # With ground truth labels
    python tools/dedup_benchmark.py ./frames/ --ground-truth labels.json
"""

import sys
import os
import argparse
import time
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import itertools

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Import deduplication strategies
from core.registry.plugin_registry import PluginRegistry
from core.models.slide import RawCapture
from modules.dedup import plugin  # This registers all strategies


@dataclass
class FramePairResult:
    """Result for a single frame pair comparison."""
    frame1_idx: int
    frame2_idx: int
    frame1_name: str
    frame2_name: str
    is_duplicate: bool
    similarity_score: float
    processing_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult:
    """Results for a single strategy across all frame pairs."""
    strategy_name: str
    total_frames: int
    total_pairs: int
    duplicates_found: int
    unique_found: int
    duplicate_ratio: float
    avg_similarity: float
    min_similarity: float
    max_similarity: float
    avg_processing_time_ms: float
    total_processing_time_ms: float
    pair_results: List[FramePairResult]
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Complete benchmark result across all strategies."""
    input_path: str
    frame_count: int
    frame_size: Tuple[int, int]
    strategies: Dict[str, StrategyResult]
    ground_truth: Optional[Dict[str, bool]] = None
    accuracy_metrics: Optional[Dict[str, Dict[str, float]]] = None
    timestamp: str = ""


class DeduplicationBenchmark:
    """Benchmarks multiple deduplication strategies on a frame sequence."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.registry = PluginRegistry()
        self._available_strategies = self.registry.list_dedup_strategies()

    def log(self, msg: str):
        if self.verbose:
            print(msg)

    def load_frames(self, frames_dir: Path, max_frames: int = 500) -> List[Tuple[str, Image.Image]]:
        """Load frames from directory.

        Returns:
            List of (filename, PIL.Image) tuples
        """
        frames_dir = Path(frames_dir)  # Ensure it's a Path
        extensions = {'.png', '.jpg', '.jpeg', '.bmp'}
        files = sorted([
            f for f in frames_dir.iterdir()
            if f.suffix.lower() in extensions
        ])

        if not files:
            raise ValueError(f"No image files found in {frames_dir}")

        if len(files) > max_frames:
            self.log(f"Sampling {max_frames} frames from {len(files)} total")
            step = len(files) // max_frames
            files = files[::step][:max_frames]

        frames = []
        for f in files:
            try:
                img = Image.open(f)
                frames.append((f.name, img.copy()))
                img.close()
            except Exception as e:
                self.log(f"Warning: Could not load {f}: {e}")

        return frames

    def create_raw_capture(self, img: Image.Image, idx: int) -> RawCapture:
        """Create RawCapture from PIL Image."""
        return RawCapture(
            image=img,
            timestamp=time.time() + idx * 0.5,  # Simulate 0.5s intervals
            monitor_id=0,
            width=img.width,
            height=img.height
        )

    def benchmark_strategy(
        self,
        strategy_name: str,
        frames: List[Tuple[str, Image.Image]],
        parameters: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        """Run benchmark for a single strategy.

        Args:
            strategy_name: Name of the strategy to test
            frames: List of (filename, image) tuples
            parameters: Optional parameter overrides

        Returns:
            StrategyResult with all metrics
        """
        strategy_class = self.registry.get_dedup_strategy(strategy_name)
        strategy = strategy_class()

        # Apply parameter overrides
        if parameters:
            for key, value in parameters.items():
                if hasattr(strategy, f'_{key}'):
                    setattr(strategy, f'_{key}', value)
                elif hasattr(strategy, key):
                    setattr(strategy, key, value)

        # Initialize strategy with empty config (uses defaults)
        strategy.initialize({})

        pair_results = []
        total_time = 0

        for i in range(len(frames) - 1):
            name1, img1 = frames[i]
            name2, img2 = frames[i + 1]

            capture1 = self.create_raw_capture(img1, i)
            capture2 = self.create_raw_capture(img2, i + 1)

            start = time.perf_counter()
            is_duplicate = strategy.is_duplicate(capture2, capture1)
            elapsed = (time.perf_counter() - start) * 1000

            # get_similarity_score returns score from last comparison
            similarity = strategy.get_similarity_score()

            # Get additional metadata for grid_temporal
            metadata = {}
            if strategy_name == 'grid_temporal' and hasattr(strategy, '_current_grid_state'):
                grid_state = strategy._current_grid_state
                if grid_state:
                    block_types = {}
                    for block_id, block in grid_state.blocks.items():
                        block_types[block_id] = block.block_type.value
                    metadata['block_types'] = block_types
                    metadata['info_block_count'] = sum(
                        1 for b in grid_state.blocks.values()
                        if b.block_type.value == 'info'
                    )

            pair_results.append(FramePairResult(
                frame1_idx=i,
                frame2_idx=i + 1,
                frame1_name=name1,
                frame2_name=name2,
                is_duplicate=is_duplicate,
                similarity_score=similarity,
                processing_time_ms=elapsed,
                metadata=metadata
            ))

            total_time += elapsed

        # Calculate aggregate metrics
        duplicates = sum(1 for r in pair_results if r.is_duplicate)
        similarities = [r.similarity_score for r in pair_results]

        return StrategyResult(
            strategy_name=strategy_name,
            total_frames=len(frames),
            total_pairs=len(pair_results),
            duplicates_found=duplicates,
            unique_found=len(pair_results) - duplicates,
            duplicate_ratio=duplicates / len(pair_results) if pair_results else 0,
            avg_similarity=np.mean(similarities) if similarities else 0,
            min_similarity=min(similarities) if similarities else 0,
            max_similarity=max(similarities) if similarities else 0,
            avg_processing_time_ms=total_time / len(pair_results) if pair_results else 0,
            total_processing_time_ms=total_time,
            pair_results=pair_results,
            parameters=parameters or {}
        )

    def run_benchmark(
        self,
        frames_dir: Path,
        strategies: Optional[List[str]] = None,
        max_frames: int = 500,
        ground_truth_path: Optional[Path] = None
    ) -> BenchmarkResult:
        """Run complete benchmark across multiple strategies.

        Args:
            frames_dir: Directory containing frame images
            strategies: List of strategy names to test (None = all)
            max_frames: Maximum frames to load
            ground_truth_path: Optional path to ground truth JSON

        Returns:
            BenchmarkResult with all comparisons
        """
        self.log(f"\n{'='*70}")
        self.log("DEDUPLICATION BENCHMARK")
        self.log(f"{'='*70}\n")

        # Ensure frames_dir is a Path
        frames_dir = Path(frames_dir)

        # Load frames
        self.log(f"Loading frames from: {frames_dir}")
        frames = self.load_frames(frames_dir, max_frames)
        self.log(f"Loaded {len(frames)} frames")

        if len(frames) < 2:
            raise ValueError("Need at least 2 frames for benchmark")

        frame_size = frames[0][1].size

        # Load ground truth if provided
        ground_truth = None
        if ground_truth_path and ground_truth_path.exists():
            with open(ground_truth_path) as f:
                ground_truth = json.load(f)
            self.log(f"Loaded ground truth with {len(ground_truth)} labels")

        # Determine strategies to test
        if strategies is None:
            strategies = self._available_strategies
        else:
            # Validate strategies
            for s in strategies:
                if s not in self._available_strategies:
                    raise ValueError(f"Unknown strategy: {s}. Available: {self._available_strategies}")

        self.log(f"\nStrategies to benchmark: {strategies}")
        self.log(f"Frame pairs to analyze: {len(frames) - 1}")

        # Run benchmarks
        results = {}
        for strategy_name in strategies:
            self.log(f"\n{'-'*70}")
            self.log(f"Testing strategy: {strategy_name}")
            self.log(f"{'-'*70}")

            try:
                result = self.benchmark_strategy(strategy_name, frames)
                results[strategy_name] = result

                self.log(f"  Duplicates: {result.duplicates_found}/{result.total_pairs} ({result.duplicate_ratio*100:.1f}%)")
                self.log(f"  Avg similarity: {result.avg_similarity:.4f}")
                self.log(f"  Avg time: {result.avg_processing_time_ms:.2f}ms")

            except Exception as e:
                self.log(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()

        # Calculate accuracy if ground truth available
        accuracy_metrics = None
        if ground_truth:
            accuracy_metrics = self._calculate_accuracy(results, ground_truth)

        benchmark_result = BenchmarkResult(
            input_path=str(frames_dir),
            frame_count=len(frames),
            frame_size=frame_size,
            strategies=results,
            ground_truth=ground_truth,
            accuracy_metrics=accuracy_metrics,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )

        self._print_summary(benchmark_result)

        return benchmark_result

    def _calculate_accuracy(
        self,
        results: Dict[str, StrategyResult],
        ground_truth: Dict[str, bool]
    ) -> Dict[str, Dict[str, float]]:
        """Calculate accuracy metrics against ground truth."""
        accuracy = {}

        for strategy_name, result in results.items():
            tp = fp = tn = fn = 0

            for pair_result in result.pair_results:
                # Create key from frame names
                key = f"{pair_result.frame1_name}_{pair_result.frame2_name}"
                alt_key = f"{pair_result.frame1_idx}_{pair_result.frame2_idx}"

                # Look up ground truth
                gt_is_dup = ground_truth.get(key, ground_truth.get(alt_key))
                if gt_is_dup is None:
                    continue

                pred_is_dup = pair_result.is_duplicate

                if gt_is_dup and pred_is_dup:
                    tp += 1
                elif not gt_is_dup and pred_is_dup:
                    fp += 1
                elif not gt_is_dup and not pred_is_dup:
                    tn += 1
                else:  # gt_is_dup and not pred_is_dup
                    fn += 1

            total = tp + fp + tn + fn
            if total > 0:
                accuracy[strategy_name] = {
                    'accuracy': (tp + tn) / total,
                    'precision': tp / (tp + fp) if (tp + fp) > 0 else 0,
                    'recall': tp / (tp + fn) if (tp + fn) > 0 else 0,
                    'f1': 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0,
                    'true_positives': tp,
                    'false_positives': fp,
                    'true_negatives': tn,
                    'false_negatives': fn
                }

        return accuracy

    def _print_summary(self, result: BenchmarkResult):
        """Print benchmark summary."""
        self.log(f"\n{'='*70}")
        self.log("BENCHMARK SUMMARY")
        self.log(f"{'='*70}")

        self.log(f"\nInput: {result.input_path}")
        self.log(f"Frames: {result.frame_count}, Size: {result.frame_size[0]}x{result.frame_size[1]}")

        # Strategy comparison table
        self.log(f"\n{'Strategy':<20} {'Dups':<8} {'Ratio':<8} {'Avg Sim':<10} {'Avg Time':<12} {'Total Time':<12}")
        self.log("-" * 80)

        for name, sr in result.strategies.items():
            self.log(
                f"{name:<20} {sr.duplicates_found:<8} "
                f"{sr.duplicate_ratio*100:>5.1f}%  "
                f"{sr.avg_similarity:>8.4f}  "
                f"{sr.avg_processing_time_ms:>8.2f}ms  "
                f"{sr.total_processing_time_ms:>8.0f}ms"
            )

        # Accuracy metrics if available
        if result.accuracy_metrics:
            self.log(f"\n{'='*70}")
            self.log("ACCURACY METRICS (vs Ground Truth)")
            self.log(f"{'='*70}")

            self.log(f"\n{'Strategy':<20} {'Accuracy':<10} {'Precision':<10} {'Recall':<10} {'F1':<10}")
            self.log("-" * 60)

            for name, metrics in result.accuracy_metrics.items():
                self.log(
                    f"{name:<20} "
                    f"{metrics['accuracy']*100:>7.1f}%  "
                    f"{metrics['precision']*100:>7.1f}%  "
                    f"{metrics['recall']*100:>7.1f}%  "
                    f"{metrics['f1']*100:>7.1f}%"
                )

        # Disagreement analysis
        self.log(f"\n{'='*70}")
        self.log("DISAGREEMENT ANALYSIS")
        self.log(f"{'='*70}")

        self._analyze_disagreements(result)

        self.log(f"\n{'='*70}\n")

    def _analyze_disagreements(self, result: BenchmarkResult):
        """Analyze where strategies disagree."""
        if len(result.strategies) < 2:
            self.log("  Need at least 2 strategies for disagreement analysis")
            return

        strategy_names = list(result.strategies.keys())
        num_pairs = result.strategies[strategy_names[0]].total_pairs

        disagreements = []
        for i in range(num_pairs):
            verdicts = {}
            for name in strategy_names:
                pair_result = result.strategies[name].pair_results[i]
                verdicts[name] = pair_result.is_duplicate

            unique_verdicts = set(verdicts.values())
            if len(unique_verdicts) > 1:
                # Get frame info from first strategy
                pr = result.strategies[strategy_names[0]].pair_results[i]
                disagreements.append({
                    'pair_idx': i,
                    'frame1': pr.frame1_name,
                    'frame2': pr.frame2_name,
                    'verdicts': verdicts,
                    'similarities': {
                        name: result.strategies[name].pair_results[i].similarity_score
                        for name in strategy_names
                    }
                })

        self.log(f"\n  Disagreements: {len(disagreements)}/{num_pairs} pairs ({len(disagreements)/num_pairs*100:.1f}%)")

        if disagreements:
            self.log(f"\n  First 10 disagreements:")
            for d in disagreements[:10]:
                self.log(f"\n    Pair {d['pair_idx']}: {d['frame1']} -> {d['frame2']}")
                for name, verdict in d['verdicts'].items():
                    sim = d['similarities'][name]
                    status = "DUP" if verdict else "UNIQUE"
                    self.log(f"      {name:<20}: {status:<8} (sim: {sim:.4f})")

    def parameter_sweep(
        self,
        frames_dir: Path,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        max_frames: int = 100,
        ground_truth_path: Optional[Path] = None
    ) -> List[Tuple[Dict[str, Any], StrategyResult]]:
        """Run parameter sweep for a strategy.

        Args:
            frames_dir: Directory containing frames
            strategy_name: Strategy to sweep
            param_grid: Dict mapping param names to lists of values
            max_frames: Max frames to use
            ground_truth_path: Optional ground truth for scoring

        Returns:
            List of (parameters, result) tuples sorted by performance
        """
        self.log(f"\n{'='*70}")
        self.log(f"PARAMETER SWEEP: {strategy_name}")
        self.log(f"{'='*70}\n")

        # Load frames once
        frames = self.load_frames(frames_dir, max_frames)
        self.log(f"Loaded {len(frames)} frames")

        # Load ground truth
        ground_truth = None
        if ground_truth_path and ground_truth_path.exists():
            with open(ground_truth_path) as f:
                ground_truth = json.load(f)

        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))

        self.log(f"Testing {len(combinations)} parameter combinations")
        self.log(f"Parameters: {param_names}")

        results = []
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            self.log(f"\n[{i+1}/{len(combinations)}] Testing: {params}")

            try:
                result = self.benchmark_strategy(strategy_name, frames, params)
                results.append((params, result))

                self.log(f"  Duplicates: {result.duplicates_found}/{result.total_pairs}")
                self.log(f"  Avg similarity: {result.avg_similarity:.4f}")
                self.log(f"  Avg time: {result.avg_processing_time_ms:.2f}ms")

            except Exception as e:
                self.log(f"  ERROR: {e}")

        # Sort by duplicate ratio (or accuracy if ground truth available)
        if ground_truth:
            # Sort by F1 score
            def score_fn(item):
                params, result = item
                accuracy = self._calculate_accuracy({strategy_name: result}, ground_truth)
                return accuracy.get(strategy_name, {}).get('f1', 0)
            results.sort(key=score_fn, reverse=True)
        else:
            # Sort by avg similarity (higher = more conservative)
            results.sort(key=lambda x: x[1].avg_similarity, reverse=True)

        # Print top results
        self.log(f"\n{'='*70}")
        self.log("TOP 10 PARAMETER COMBINATIONS")
        self.log(f"{'='*70}\n")

        for i, (params, result) in enumerate(results[:10]):
            self.log(f"\n{i+1}. Parameters: {params}")
            self.log(f"   Duplicates: {result.duplicates_found}/{result.total_pairs} ({result.duplicate_ratio*100:.1f}%)")
            self.log(f"   Avg similarity: {result.avg_similarity:.4f}")
            self.log(f"   Avg time: {result.avg_processing_time_ms:.2f}ms")

        return results


def create_visual_comparison(
    benchmark_result: BenchmarkResult,
    frames_dir: Path,
    output_path: Path,
    max_pairs: int = 20
):
    """Create visual comparison of strategy results."""
    # Load a subset of frames for visualization
    extensions = {'.png', '.jpg', '.jpeg', '.bmp'}
    files = sorted([
        f for f in frames_dir.iterdir()
        if f.suffix.lower() in extensions
    ])[:max_pairs + 1]

    strategy_names = list(benchmark_result.strategies.keys())
    num_strategies = len(strategy_names)
    num_pairs = min(max_pairs, len(files) - 1)

    # Create visualization
    thumb_size = (200, 150)
    padding = 10
    header_height = 30

    # Calculate dimensions
    cell_width = thumb_size[0] * 2 + padding * 3
    cell_height = thumb_size[1] + header_height + padding * 2

    grid_width = cell_width * num_strategies + padding
    grid_height = cell_height * num_pairs + header_height + padding * 2

    # Create image
    img = Image.new('RGB', (grid_width, grid_height), (30, 30, 40))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        font = ImageFont.load_default()
        font_small = font

    # Draw column headers
    for col, name in enumerate(strategy_names):
        x = col * cell_width + padding + cell_width // 2
        draw.text((x, padding), name, fill=(255, 255, 255), font=font, anchor="mt")

    # Draw each pair
    for row in range(num_pairs):
        y_base = header_height + padding + row * cell_height

        for col, strategy_name in enumerate(strategy_names):
            x_base = col * cell_width + padding

            result = benchmark_result.strategies[strategy_name]
            pair_result = result.pair_results[row]

            # Load and resize thumbnails
            frame1 = Image.open(files[row]).convert('RGB')
            frame2 = Image.open(files[row + 1]).convert('RGB')

            thumb1 = frame1.copy()
            thumb1.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            thumb2 = frame2.copy()
            thumb2.thumbnail(thumb_size, Image.Resampling.LANCZOS)

            # Paste thumbnails
            img.paste(thumb1, (x_base + padding, y_base + header_height))
            img.paste(thumb2, (x_base + padding + thumb_size[0] + padding, y_base + header_height))

            # Draw verdict
            verdict = "DUP" if pair_result.is_duplicate else "UNIQUE"
            color = (16, 185, 129) if pair_result.is_duplicate else (239, 68, 68)

            text = f"{verdict} (sim: {pair_result.similarity_score:.3f})"
            draw.text(
                (x_base + cell_width // 2, y_base + 5),
                text, fill=color, font=font_small, anchor="mt"
            )

            frame1.close()
            frame2.close()

    img.save(output_path)
    print(f"Visual comparison saved to: {output_path}")


def create_grid_temporal_visualization(
    benchmark_result: BenchmarkResult,
    frames_dir: Path,
    output_path: Path,
    frame_idx: int = 0
):
    """Create visualization of grid_temporal block classifications."""
    if 'grid_temporal' not in benchmark_result.strategies:
        print("grid_temporal strategy not in results")
        return

    result = benchmark_result.strategies['grid_temporal']
    if frame_idx >= len(result.pair_results):
        frame_idx = len(result.pair_results) - 1

    pair_result = result.pair_results[frame_idx]
    block_types = pair_result.metadata.get('block_types', {})

    if not block_types:
        print("No block type data available")
        return

    # Load the frame
    extensions = {'.png', '.jpg', '.jpeg', '.bmp'}
    files = sorted([
        f for f in frames_dir.iterdir()
        if f.suffix.lower() in extensions
    ])

    if frame_idx + 1 >= len(files):
        return

    frame = Image.open(files[frame_idx + 1]).convert('RGB')
    draw = ImageDraw.Draw(frame, 'RGBA')

    # Determine grid size (default 8x12)
    grid_rows = 8
    grid_cols = 12

    block_h = frame.height // grid_rows
    block_w = frame.width // grid_cols

    # Color mapping
    colors = {
        'unknown': (128, 128, 128, 100),  # Gray
        'static': (59, 130, 246, 100),     # Blue
        'info': (16, 185, 129, 100),       # Green
        'video': (239, 68, 68, 100)        # Red
    }

    border_colors = {
        'unknown': (128, 128, 128, 200),
        'static': (59, 130, 246, 200),
        'info': (16, 185, 129, 200),
        'video': (239, 68, 68, 200)
    }

    # Draw blocks
    for block_id, block_type in block_types.items():
        row, col = map(int, block_id.split('_'))
        x1 = col * block_w
        y1 = row * block_h
        x2 = x1 + block_w
        y2 = y1 + block_h

        fill_color = colors.get(block_type, colors['unknown'])
        border_color = border_colors.get(block_type, border_colors['unknown'])

        draw.rectangle([x1, y1, x2, y2], fill=fill_color, outline=border_color, width=2)

    # Add legend
    legend_y = 10
    legend_x = 10
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except:
        font = ImageFont.load_default()

    for label, color in [('STATIC', 'static'), ('INFO', 'info'), ('VIDEO', 'video')]:
        draw.rectangle(
            [legend_x, legend_y, legend_x + 20, legend_y + 20],
            fill=colors[color][:3] + (255,),
            outline=(255, 255, 255)
        )
        draw.text((legend_x + 25, legend_y + 3), label, fill=(255, 255, 255), font=font)
        legend_y += 30

    # Add info
    info_text = f"Frame {frame_idx + 1}: {pair_result.frame2_name}"
    info_text += f"\nSimilarity: {pair_result.similarity_score:.4f}"
    info_text += f"\nVerdict: {'DUPLICATE' if pair_result.is_duplicate else 'UNIQUE'}"
    info_text += f"\nINFO blocks: {pair_result.metadata.get('info_block_count', 'N/A')}"

    draw.rectangle([legend_x - 5, legend_y, legend_x + 200, legend_y + 80], fill=(0, 0, 0, 180))
    draw.text((legend_x, legend_y + 5), info_text, fill=(255, 255, 255), font=font)

    frame.save(output_path)
    print(f"Grid temporal visualization saved to: {output_path}")


def save_benchmark_json(result: BenchmarkResult, output_path: Path):
    """Save benchmark result as JSON."""
    def to_serializable(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif hasattr(obj, '__dict__'):
            return {k: to_serializable(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, dict):
            return {k: to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [to_serializable(x) for x in obj]
        return obj

    data = to_serializable(asdict(result) if hasattr(result, '__dataclass_fields__') else result.__dict__)

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    print(f"Benchmark results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark deduplication strategies on frame sequences',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('frames_dir', help='Directory containing frame images')
    parser.add_argument('--strategies', '-s', help='Comma-separated list of strategies to test')
    parser.add_argument('--output-dir', '-o', default='./benchmark_output',
                       help='Output directory for reports')
    parser.add_argument('--max-frames', type=int, default=100,
                       help='Maximum frames to analyze (default: 100)')
    parser.add_argument('--visual', '-v', action='store_true',
                       help='Generate visual comparison')
    parser.add_argument('--json', '-j', action='store_true',
                       help='Save JSON report')
    parser.add_argument('--ground-truth', '-g', help='Path to ground truth JSON file')
    parser.add_argument('--sweep', help='Strategy name for parameter sweep')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Minimal output')

    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    if not frames_dir.exists() or not frames_dir.is_dir():
        print(f"Error: {frames_dir} is not a valid directory")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark = DeduplicationBenchmark(verbose=not args.quiet)

    # Parse strategies
    strategies = None
    if args.strategies:
        strategies = [s.strip() for s in args.strategies.split(',')]

    ground_truth_path = Path(args.ground_truth) if args.ground_truth else None

    # Parameter sweep mode
    if args.sweep:
        # Define parameter grids for each strategy
        param_grids = {
            'grid_temporal': {
                'duplicate_threshold': [0.85, 0.90, 0.92, 0.95],
                'static_threshold': [0.05, 0.10, 0.15],
                'video_threshold': [0.6, 0.7, 0.8],
            },
            'perceptual': {
                'similarity_threshold': [0.90, 0.92, 0.95, 0.97],
            },
            'hybrid': {
                'perceptual_weight': [0.5, 0.6, 0.7, 0.8],
            }
        }

        if args.sweep not in param_grids:
            print(f"No parameter grid defined for {args.sweep}")
            print(f"Available: {list(param_grids.keys())}")
            sys.exit(1)

        results = benchmark.parameter_sweep(
            frames_dir,
            args.sweep,
            param_grids[args.sweep],
            args.max_frames,
            ground_truth_path
        )

        # Save sweep results
        if args.json:
            sweep_data = [
                {'parameters': params, 'metrics': asdict(result)}
                for params, result in results
            ]
            sweep_path = output_dir / f"sweep_{args.sweep}_{int(time.time())}.json"
            with open(sweep_path, 'w') as f:
                json.dump(sweep_data, f, indent=2, default=str)
            print(f"Sweep results saved to: {sweep_path}")

    else:
        # Standard benchmark mode
        result = benchmark.run_benchmark(
            frames_dir,
            strategies,
            args.max_frames,
            ground_truth_path
        )

        # Generate outputs
        timestamp = int(time.time())

        if args.visual:
            visual_path = output_dir / f"comparison_{timestamp}.png"
            create_visual_comparison(result, frames_dir, visual_path)

            if 'grid_temporal' in result.strategies:
                grid_viz_path = output_dir / f"grid_temporal_{timestamp}.png"
                create_grid_temporal_visualization(result, frames_dir, grid_viz_path)

        if args.json:
            json_path = output_dir / f"benchmark_{timestamp}.json"
            save_benchmark_json(result, json_path)


if __name__ == '__main__':
    main()
