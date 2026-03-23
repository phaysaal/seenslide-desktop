#!/usr/bin/env python3
"""Deduplication Analyzer Tool

Analyzes two images using all deduplication strategies and provides
detailed reports to help identify weaknesses in the system.

Usage:
    python tools/dedup_analyzer.py <image1> <image2> [--output-dir <dir>]

Examples:
    python tools/dedup_analyzer.py slide1.png slide2.png
    python tools/dedup_analyzer.py slide1.png slide2.png --output-dir ./analysis
    python tools/dedup_analyzer.py slide1.png slide2.png --visual
"""

import sys
import os
import argparse
import time
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imagehash

# Try to import cv2, but make it optional
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("Note: OpenCV (cv2) not available. Some features will use fallback implementations.")


@dataclass
class ImageInfo:
    """Information about an image."""
    path: str
    width: int
    height: int
    mode: str
    file_size_bytes: int
    megapixels: float


@dataclass
class HashAnalysis:
    """Results from hash-based comparison."""
    md5_hash_1: str
    md5_hash_2: str
    sha256_hash_1: str
    sha256_hash_2: str
    md5_match: bool
    sha256_match: bool
    is_duplicate: bool
    verdict: str


@dataclass
class PerceptualAnalysis:
    """Results from perceptual hash comparison."""
    phash_1: str
    phash_2: str
    ahash_1: str
    ahash_2: str
    dhash_1: str
    dhash_2: str
    whash_1: str
    whash_2: str
    phash_distance: int
    ahash_distance: int
    dhash_distance: int
    whash_distance: int
    phash_similarity: float
    ahash_similarity: float
    dhash_similarity: float
    whash_similarity: float
    avg_similarity: float
    is_duplicate_at_95: bool
    is_duplicate_at_92: bool
    is_duplicate_at_90: bool
    verdict: str


@dataclass
class PixelAnalysis:
    """Pixel-level comparison analysis."""
    total_pixels: int
    identical_pixels: int
    different_pixels: int
    identical_ratio: float
    different_ratio: float
    max_pixel_diff: int
    avg_pixel_diff: float
    std_pixel_diff: float
    diff_histogram: Dict[str, int]
    hotspot_regions: List[Dict[str, Any]]
    verdict: str


@dataclass
class StructuralAnalysis:
    """Structural similarity analysis (SSIM)."""
    ssim_score: float
    ssim_map_stats: Dict[str, float]
    is_duplicate_at_95: bool
    is_duplicate_at_92: bool
    verdict: str


@dataclass
class RegionAnalysis:
    """Analysis of different image regions."""
    quadrant_similarities: Dict[str, float]
    center_similarity: float
    border_similarity: float
    weakest_region: str
    strongest_region: str
    verdict: str


@dataclass
class FullReport:
    """Complete analysis report."""
    timestamp: str
    image1_info: ImageInfo
    image2_info: ImageInfo
    hash_analysis: HashAnalysis
    perceptual_analysis: PerceptualAnalysis
    pixel_analysis: PixelAnalysis
    structural_analysis: StructuralAnalysis
    region_analysis: RegionAnalysis
    overall_verdict: str
    recommendations: List[str]
    processing_time_ms: float


class DeduplicationAnalyzer:
    """Analyzes image pairs using multiple deduplication strategies."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def log(self, msg: str):
        if self.verbose:
            print(msg)

    def analyze(self, image1_path: str, image2_path: str) -> FullReport:
        """Run complete analysis on two images.

        Args:
            image1_path: Path to first image
            image2_path: Path to second image

        Returns:
            FullReport with all analysis results
        """
        start_time = time.time()

        self.log(f"\n{'='*70}")
        self.log("DEDUPLICATION ANALYSIS REPORT")
        self.log(f"{'='*70}\n")

        # Load images
        self.log("Loading images...")
        img1 = Image.open(image1_path)
        img2 = Image.open(image2_path)

        # Get image info
        img1_info = self._get_image_info(image1_path, img1)
        img2_info = self._get_image_info(image2_path, img2)

        self._print_image_info(img1_info, "Image 1")
        self._print_image_info(img2_info, "Image 2")

        # Resize if dimensions don't match
        if img1.size != img2.size:
            self.log(f"\n[WARNING] Image dimensions differ! Resizing image 2 to match image 1.")
            img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

        # Run all analyses
        self.log(f"\n{'-'*70}")
        self.log("ANALYSIS RESULTS")
        self.log(f"{'-'*70}")

        hash_analysis = self._analyze_hash(img1, img2)
        perceptual_analysis = self._analyze_perceptual(img1, img2)
        pixel_analysis = self._analyze_pixels(img1, img2)
        structural_analysis = self._analyze_structural(img1, img2)
        region_analysis = self._analyze_regions(img1, img2)

        # Generate overall verdict and recommendations
        overall_verdict, recommendations = self._generate_verdict(
            hash_analysis, perceptual_analysis, pixel_analysis,
            structural_analysis, region_analysis
        )

        processing_time = (time.time() - start_time) * 1000

        # Create report
        report = FullReport(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            image1_info=img1_info,
            image2_info=img2_info,
            hash_analysis=hash_analysis,
            perceptual_analysis=perceptual_analysis,
            pixel_analysis=pixel_analysis,
            structural_analysis=structural_analysis,
            region_analysis=region_analysis,
            overall_verdict=overall_verdict,
            recommendations=recommendations,
            processing_time_ms=processing_time
        )

        self._print_summary(report)

        return report

    def _get_image_info(self, path: str, img: Image.Image) -> ImageInfo:
        """Extract image information."""
        file_size = os.path.getsize(path)
        return ImageInfo(
            path=path,
            width=img.width,
            height=img.height,
            mode=img.mode,
            file_size_bytes=file_size,
            megapixels=round(img.width * img.height / 1_000_000, 2)
        )

    def _print_image_info(self, info: ImageInfo, label: str):
        """Print image information."""
        self.log(f"\n{label}:")
        self.log(f"  Path: {info.path}")
        self.log(f"  Dimensions: {info.width} x {info.height} ({info.megapixels} MP)")
        self.log(f"  Mode: {info.mode}")
        self.log(f"  File size: {info.file_size_bytes:,} bytes")

    def _analyze_hash(self, img1: Image.Image, img2: Image.Image) -> HashAnalysis:
        """Analyze using cryptographic hashes."""
        self.log("\n[1] HASH ANALYSIS (Exact Match)")

        import hashlib

        # Get raw bytes
        bytes1 = img1.tobytes()
        bytes2 = img2.tobytes()

        # Compute hashes
        md5_1 = hashlib.md5(bytes1).hexdigest()
        md5_2 = hashlib.md5(bytes2).hexdigest()
        sha256_1 = hashlib.sha256(bytes1).hexdigest()
        sha256_2 = hashlib.sha256(bytes2).hexdigest()

        md5_match = md5_1 == md5_2
        sha256_match = sha256_1 == sha256_2
        is_duplicate = md5_match and sha256_match

        if is_duplicate:
            verdict = "DUPLICATE - Pixel-perfect identical images"
        else:
            verdict = "UNIQUE - Images differ at pixel level"

        self.log(f"  MD5 Image 1:    {md5_1}")
        self.log(f"  MD5 Image 2:    {md5_2}")
        self.log(f"  MD5 Match:      {md5_match}")
        self.log(f"  SHA256 Match:   {sha256_match}")
        self.log(f"  Verdict:        {verdict}")

        return HashAnalysis(
            md5_hash_1=md5_1,
            md5_hash_2=md5_2,
            sha256_hash_1=sha256_1,
            sha256_hash_2=sha256_2,
            md5_match=md5_match,
            sha256_match=sha256_match,
            is_duplicate=is_duplicate,
            verdict=verdict
        )

    def _analyze_perceptual(self, img1: Image.Image, img2: Image.Image) -> PerceptualAnalysis:
        """Analyze using perceptual hashes."""
        self.log("\n[2] PERCEPTUAL HASH ANALYSIS (Visual Similarity)")

        # Compute various perceptual hashes
        phash1 = imagehash.phash(img1, hash_size=8)
        phash2 = imagehash.phash(img2, hash_size=8)
        ahash1 = imagehash.average_hash(img1, hash_size=8)
        ahash2 = imagehash.average_hash(img2, hash_size=8)
        dhash1 = imagehash.dhash(img1, hash_size=8)
        dhash2 = imagehash.dhash(img2, hash_size=8)
        whash1 = imagehash.whash(img1, hash_size=8)
        whash2 = imagehash.whash(img2, hash_size=8)

        # Calculate distances (Hamming distance)
        phash_dist = phash1 - phash2
        ahash_dist = ahash1 - ahash2
        dhash_dist = dhash1 - dhash2
        whash_dist = whash1 - whash2

        # Convert to similarity (0-1)
        max_dist = 64  # 8x8 hash
        phash_sim = 1.0 - (phash_dist / max_dist)
        ahash_sim = 1.0 - (ahash_dist / max_dist)
        dhash_sim = 1.0 - (dhash_dist / max_dist)
        whash_sim = 1.0 - (whash_dist / max_dist)
        avg_sim = (phash_sim + ahash_sim + dhash_sim + whash_sim) / 4

        self.log(f"  {'Hash Type':<12} {'Image 1':<20} {'Image 2':<20} {'Distance':<10} {'Similarity':<10}")
        self.log(f"  {'-'*72}")
        self.log(f"  {'pHash':<12} {str(phash1):<20} {str(phash2):<20} {phash_dist:<10} {phash_sim:.4f}")
        self.log(f"  {'aHash':<12} {str(ahash1):<20} {str(ahash2):<20} {ahash_dist:<10} {ahash_sim:.4f}")
        self.log(f"  {'dHash':<12} {str(dhash1):<20} {str(dhash2):<20} {dhash_dist:<10} {dhash_sim:.4f}")
        self.log(f"  {'wHash':<12} {str(whash1):<20} {str(whash2):<20} {whash_dist:<10} {whash_sim:.4f}")
        self.log(f"  {'-'*72}")
        self.log(f"  {'Average':<12} {'':<20} {'':<20} {'':<10} {avg_sim:.4f}")

        is_dup_95 = phash_sim >= 0.95
        is_dup_92 = phash_sim >= 0.92
        is_dup_90 = phash_sim >= 0.90

        self.log(f"\n  Duplicate at 95% threshold: {is_dup_95}")
        self.log(f"  Duplicate at 92% threshold: {is_dup_92}")
        self.log(f"  Duplicate at 90% threshold: {is_dup_90}")

        if phash_sim >= 0.95:
            verdict = "DUPLICATE - Very high visual similarity"
        elif phash_sim >= 0.90:
            verdict = "LIKELY DUPLICATE - High visual similarity"
        elif phash_sim >= 0.80:
            verdict = "POSSIBLY RELATED - Moderate similarity"
        else:
            verdict = "UNIQUE - Low visual similarity"

        self.log(f"  Verdict: {verdict}")

        return PerceptualAnalysis(
            phash_1=str(phash1),
            phash_2=str(phash2),
            ahash_1=str(ahash1),
            ahash_2=str(ahash2),
            dhash_1=str(dhash1),
            dhash_2=str(dhash2),
            whash_1=str(whash1),
            whash_2=str(whash2),
            phash_distance=phash_dist,
            ahash_distance=ahash_dist,
            dhash_distance=dhash_dist,
            whash_distance=whash_dist,
            phash_similarity=phash_sim,
            ahash_similarity=ahash_sim,
            dhash_similarity=dhash_sim,
            whash_similarity=whash_sim,
            avg_similarity=avg_sim,
            is_duplicate_at_95=is_dup_95,
            is_duplicate_at_92=is_dup_92,
            is_duplicate_at_90=is_dup_90,
            verdict=verdict
        )

    def _analyze_pixels(self, img1: Image.Image, img2: Image.Image) -> PixelAnalysis:
        """Analyze pixel-level differences."""
        self.log("\n[3] PIXEL-LEVEL ANALYSIS")

        # Convert to numpy arrays (grayscale for comparison)
        arr1 = np.array(img1.convert('L'), dtype=np.float32)
        arr2 = np.array(img2.convert('L'), dtype=np.float32)

        # Compute difference
        diff = np.abs(arr1 - arr2)

        total_pixels = arr1.size
        identical_pixels = int(np.sum(diff == 0))
        different_pixels = total_pixels - identical_pixels

        identical_ratio = identical_pixels / total_pixels
        different_ratio = different_pixels / total_pixels

        max_diff = float(np.max(diff))
        avg_diff = float(np.mean(diff))
        std_diff = float(np.std(diff))

        # Difference histogram (grouped)
        diff_histogram = {
            "0 (identical)": int(np.sum(diff == 0)),
            "1-5 (minor)": int(np.sum((diff >= 1) & (diff <= 5))),
            "6-15 (small)": int(np.sum((diff >= 6) & (diff <= 15))),
            "16-30 (medium)": int(np.sum((diff >= 16) & (diff <= 30))),
            "31-50 (large)": int(np.sum((diff >= 31) & (diff <= 50))),
            "51+ (major)": int(np.sum(diff > 50))
        }

        self.log(f"  Total pixels:       {total_pixels:,}")
        self.log(f"  Identical pixels:   {identical_pixels:,} ({identical_ratio*100:.2f}%)")
        self.log(f"  Different pixels:   {different_pixels:,} ({different_ratio*100:.2f}%)")
        self.log(f"  Max pixel diff:     {max_diff:.0f}")
        self.log(f"  Avg pixel diff:     {avg_diff:.2f}")
        self.log(f"  Std pixel diff:     {std_diff:.2f}")

        self.log(f"\n  Difference Distribution:")
        for range_name, count in diff_histogram.items():
            pct = count / total_pixels * 100
            bar = '#' * int(pct / 2)
            self.log(f"    {range_name:<20} {count:>10,} ({pct:>6.2f}%) {bar}")

        # Find hotspot regions (areas with most changes)
        hotspots = self._find_hotspots(diff)

        self.log(f"\n  Change Hotspots (regions with most differences):")
        for i, hotspot in enumerate(hotspots[:5]):
            self.log(f"    {i+1}. Region ({hotspot['x']}, {hotspot['y']}) - "
                    f"{hotspot['width']}x{hotspot['height']}: "
                    f"avg_diff={hotspot['avg_diff']:.1f}")

        if identical_ratio >= 0.99:
            verdict = "NEAR-IDENTICAL - 99%+ pixels match"
        elif identical_ratio >= 0.95:
            verdict = "VERY SIMILAR - 95%+ pixels match"
        elif identical_ratio >= 0.90:
            verdict = "SIMILAR - 90%+ pixels match"
        else:
            verdict = f"DIFFERENT - Only {identical_ratio*100:.1f}% pixels match"

        self.log(f"  Verdict: {verdict}")

        return PixelAnalysis(
            total_pixels=total_pixels,
            identical_pixels=identical_pixels,
            different_pixels=different_pixels,
            identical_ratio=identical_ratio,
            different_ratio=different_ratio,
            max_pixel_diff=int(max_diff),
            avg_pixel_diff=avg_diff,
            std_pixel_diff=std_diff,
            diff_histogram=diff_histogram,
            hotspot_regions=hotspots[:5],
            verdict=verdict
        )

    def _find_hotspots(self, diff: np.ndarray, grid_size: int = 8) -> List[Dict[str, Any]]:
        """Find regions with highest average differences."""
        h, w = diff.shape
        cell_h = h // grid_size
        cell_w = w // grid_size

        hotspots = []
        for i in range(grid_size):
            for j in range(grid_size):
                y1, y2 = i * cell_h, (i + 1) * cell_h
                x1, x2 = j * cell_w, (j + 1) * cell_w
                region = diff[y1:y2, x1:x2]
                avg_diff = float(np.mean(region))
                hotspots.append({
                    'x': x1,
                    'y': y1,
                    'width': cell_w,
                    'height': cell_h,
                    'avg_diff': avg_diff
                })

        # Sort by average difference (descending)
        hotspots.sort(key=lambda h: h['avg_diff'], reverse=True)
        return hotspots

    def _analyze_structural(self, img1: Image.Image, img2: Image.Image) -> StructuralAnalysis:
        """Analyze structural similarity (SSIM)."""
        self.log("\n[4] STRUCTURAL SIMILARITY (SSIM)")

        # Convert to grayscale numpy arrays
        arr1 = np.array(img1.convert('L'))
        arr2 = np.array(img2.convert('L'))

        # Compute SSIM
        ssim_score, ssim_map = self._compute_ssim(arr1, arr2)

        ssim_map_stats = {
            "min": float(np.min(ssim_map)),
            "max": float(np.max(ssim_map)),
            "mean": float(np.mean(ssim_map)),
            "std": float(np.std(ssim_map))
        }

        self.log(f"  SSIM Score:     {ssim_score:.4f}")
        self.log(f"  SSIM Map Min:   {ssim_map_stats['min']:.4f}")
        self.log(f"  SSIM Map Max:   {ssim_map_stats['max']:.4f}")
        self.log(f"  SSIM Map Mean:  {ssim_map_stats['mean']:.4f}")
        self.log(f"  SSIM Map Std:   {ssim_map_stats['std']:.4f}")

        is_dup_95 = ssim_score >= 0.95
        is_dup_92 = ssim_score >= 0.92

        if ssim_score >= 0.95:
            verdict = "DUPLICATE - Structurally identical"
        elif ssim_score >= 0.90:
            verdict = "LIKELY DUPLICATE - Very similar structure"
        elif ssim_score >= 0.80:
            verdict = "SIMILAR - Moderate structural similarity"
        else:
            verdict = "DIFFERENT - Low structural similarity"

        self.log(f"  Verdict: {verdict}")

        return StructuralAnalysis(
            ssim_score=ssim_score,
            ssim_map_stats=ssim_map_stats,
            is_duplicate_at_95=is_dup_95,
            is_duplicate_at_92=is_dup_92,
            verdict=verdict
        )

    def _compute_ssim(self, img1: np.ndarray, img2: np.ndarray,
                      window_size: int = 11) -> Tuple[float, np.ndarray]:
        """Compute Structural Similarity Index."""
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        img1 = img1.astype(np.float64)
        img2 = img2.astype(np.float64)

        if HAS_CV2:
            kernel = cv2.getGaussianKernel(window_size, 1.5)
            window = np.outer(kernel, kernel.transpose())

            mu1 = cv2.filter2D(img1, -1, window)[5:-5, 5:-5]
            mu2 = cv2.filter2D(img2, -1, window)[5:-5, 5:-5]

            mu1_sq = mu1 ** 2
            mu2_sq = mu2 ** 2
            mu1_mu2 = mu1 * mu2

            sigma1_sq = cv2.filter2D(img1 ** 2, -1, window)[5:-5, 5:-5] - mu1_sq
            sigma2_sq = cv2.filter2D(img2 ** 2, -1, window)[5:-5, 5:-5] - mu2_sq
            sigma12 = cv2.filter2D(img1 * img2, -1, window)[5:-5, 5:-5] - mu1_mu2

            ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                       ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))

            return float(np.mean(ssim_map)), ssim_map
        else:
            # Simplified SSIM without cv2 (block-based approach)
            return self._compute_ssim_simple(img1, img2)

    def _compute_ssim_simple(self, img1: np.ndarray, img2: np.ndarray,
                             block_size: int = 8) -> Tuple[float, np.ndarray]:
        """Simplified SSIM computation without OpenCV."""
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        h, w = img1.shape
        ssim_values = []

        # Compute block-wise SSIM
        for i in range(0, h - block_size, block_size):
            for j in range(0, w - block_size, block_size):
                block1 = img1[i:i+block_size, j:j+block_size].flatten()
                block2 = img2[i:i+block_size, j:j+block_size].flatten()

                mu1 = np.mean(block1)
                mu2 = np.mean(block2)
                sigma1_sq = np.var(block1)
                sigma2_sq = np.var(block2)
                sigma12 = np.cov(block1, block2)[0, 1]

                ssim = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / \
                       ((mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2))
                ssim_values.append(ssim)

        ssim_map = np.array(ssim_values).reshape(-1, 1)  # Simplified map
        return float(np.mean(ssim_values)), ssim_map

    def _analyze_regions(self, img1: Image.Image, img2: Image.Image) -> RegionAnalysis:
        """Analyze different regions of the images."""
        self.log("\n[5] REGION-BASED ANALYSIS")

        w, h = img1.size

        # Define regions
        regions = {
            "top-left": (0, 0, w//2, h//2),
            "top-right": (w//2, 0, w, h//2),
            "bottom-left": (0, h//2, w//2, h),
            "bottom-right": (w//2, h//2, w, h),
            "center": (w//4, h//4, 3*w//4, 3*h//4)
        }

        # Border region (outer 10%)
        border_size = min(w, h) // 10

        quadrant_sims = {}

        self.log(f"  {'Region':<15} {'Similarity':<12} {'Status'}")
        self.log(f"  {'-'*45}")

        for name, (x1, y1, x2, y2) in regions.items():
            region1 = img1.crop((x1, y1, x2, y2))
            region2 = img2.crop((x1, y1, x2, y2))

            # Use perceptual hash for region comparison
            hash1 = imagehash.phash(region1, hash_size=8)
            hash2 = imagehash.phash(region2, hash_size=8)
            similarity = 1.0 - ((hash1 - hash2) / 64)

            quadrant_sims[name] = similarity
            status = "MATCH" if similarity >= 0.95 else "DIFFER" if similarity < 0.85 else "SIMILAR"
            self.log(f"  {name:<15} {similarity:.4f}       {status}")

        # Find weakest and strongest regions
        weakest = min(quadrant_sims, key=quadrant_sims.get)
        strongest = max(quadrant_sims, key=quadrant_sims.get)

        center_sim = quadrant_sims.get("center", 0)

        # Calculate border similarity (average of corners)
        corner_sims = [quadrant_sims[k] for k in ["top-left", "top-right", "bottom-left", "bottom-right"]]
        border_sim = sum(corner_sims) / len(corner_sims)

        self.log(f"\n  Weakest region:   {weakest} ({quadrant_sims[weakest]:.4f})")
        self.log(f"  Strongest region: {strongest} ({quadrant_sims[strongest]:.4f})")
        self.log(f"  Center similarity: {center_sim:.4f}")
        self.log(f"  Border similarity: {border_sim:.4f}")

        if center_sim >= 0.95 and border_sim >= 0.95:
            verdict = "UNIFORM MATCH - All regions similar"
        elif center_sim >= 0.95:
            verdict = "CENTER MATCH - Slide content same, borders differ"
        elif border_sim >= 0.95:
            verdict = "BORDER MATCH - Center content changed"
        else:
            verdict = "VARIED - Different regions show different changes"

        self.log(f"  Verdict: {verdict}")

        return RegionAnalysis(
            quadrant_similarities=quadrant_sims,
            center_similarity=center_sim,
            border_similarity=border_sim,
            weakest_region=weakest,
            strongest_region=strongest,
            verdict=verdict
        )

    def _generate_verdict(self, hash_analysis: HashAnalysis,
                         perceptual_analysis: PerceptualAnalysis,
                         pixel_analysis: PixelAnalysis,
                         structural_analysis: StructuralAnalysis,
                         region_analysis: RegionAnalysis) -> Tuple[str, List[str]]:
        """Generate overall verdict and recommendations."""

        recommendations = []

        # Scoring
        scores = {
            'hash': 1.0 if hash_analysis.is_duplicate else 0.0,
            'perceptual': perceptual_analysis.phash_similarity,
            'pixel': pixel_analysis.identical_ratio,
            'structural': structural_analysis.ssim_score,
            'region_center': region_analysis.center_similarity
        }

        avg_score = sum(scores.values()) / len(scores)

        # Determine verdict
        if hash_analysis.is_duplicate:
            verdict = "DEFINITE DUPLICATE - Pixel-perfect match"
        elif perceptual_analysis.phash_similarity >= 0.95 and structural_analysis.ssim_score >= 0.95:
            verdict = "VERY LIKELY DUPLICATE - High perceptual and structural similarity"
        elif perceptual_analysis.phash_similarity >= 0.92:
            verdict = "LIKELY DUPLICATE - High perceptual similarity"
        elif perceptual_analysis.phash_similarity >= 0.85:
            verdict = "POSSIBLY DUPLICATE - Moderate similarity, review recommended"
        elif perceptual_analysis.phash_similarity >= 0.70:
            verdict = "POSSIBLY RELATED - Some similarity detected"
        else:
            verdict = "UNIQUE - Images are different"

        # Generate recommendations
        if not hash_analysis.is_duplicate and perceptual_analysis.phash_similarity >= 0.90:
            recommendations.append(
                "Hash strategy would miss this duplicate. Consider using perceptual strategy."
            )

        if perceptual_analysis.phash_similarity < 0.95 and structural_analysis.ssim_score >= 0.95:
            recommendations.append(
                "SSIM detects similarity that pHash misses. Images may have color/contrast changes."
            )

        if region_analysis.center_similarity >= 0.95 and region_analysis.border_similarity < 0.90:
            recommendations.append(
                "Center content is same but borders differ. Possible cursor movement or UI change. "
                "Consider using crop region to focus on slide content."
            )

        if pixel_analysis.different_ratio > 0.01 and pixel_analysis.different_ratio < 0.05:
            recommendations.append(
                f"Small pixel differences ({pixel_analysis.different_ratio*100:.1f}%) detected. "
                "Could be compression artifacts, cursor, or minor animations."
            )

        weakest = region_analysis.weakest_region
        if region_analysis.quadrant_similarities[weakest] < 0.85:
            recommendations.append(
                f"Region '{weakest}' shows most changes. If this is a video/webcam area, "
                "consider using adaptive strategy to ignore it."
            )

        if perceptual_analysis.phash_similarity >= 0.92 and perceptual_analysis.phash_similarity < 0.95:
            recommendations.append(
                "Similarity is between 92-95%. Current threshold (0.95) would mark as unique. "
                "Consider lowering threshold to 0.92 if these should be duplicates."
            )

        if not recommendations:
            if hash_analysis.is_duplicate:
                recommendations.append("Images are identical. Any deduplication strategy will work.")
            else:
                recommendations.append("Images are clearly different. No strategy issues detected.")

        return verdict, recommendations

    def _print_summary(self, report: FullReport):
        """Print summary section."""
        self.log(f"\n{'='*70}")
        self.log("SUMMARY")
        self.log(f"{'='*70}")

        self.log(f"\n  Overall Verdict: {report.overall_verdict}")
        self.log(f"  Processing Time: {report.processing_time_ms:.2f} ms")

        self.log(f"\n  Strategy Results:")
        self.log(f"    Hash Strategy:      {'DUPLICATE' if report.hash_analysis.is_duplicate else 'UNIQUE'}")
        self.log(f"    Perceptual (0.95):  {'DUPLICATE' if report.perceptual_analysis.is_duplicate_at_95 else 'UNIQUE'}")
        self.log(f"    Perceptual (0.92):  {'DUPLICATE' if report.perceptual_analysis.is_duplicate_at_92 else 'UNIQUE'}")
        self.log(f"    SSIM (0.95):        {'DUPLICATE' if report.structural_analysis.is_duplicate_at_95 else 'UNIQUE'}")

        self.log(f"\n  Key Metrics:")
        self.log(f"    pHash Similarity:   {report.perceptual_analysis.phash_similarity:.4f}")
        self.log(f"    SSIM Score:         {report.structural_analysis.ssim_score:.4f}")
        self.log(f"    Pixel Match Rate:   {report.pixel_analysis.identical_ratio*100:.2f}%")

        self.log(f"\n  Recommendations:")
        for i, rec in enumerate(report.recommendations, 1):
            self.log(f"    {i}. {rec}")

        self.log(f"\n{'='*70}\n")

    def generate_visual_report(self, img1_path: str, img2_path: str,
                               output_path: str) -> str:
        """Generate visual difference report as an image.

        Args:
            img1_path: Path to first image
            img2_path: Path to second image
            output_path: Path for output image

        Returns:
            Path to generated image
        """
        img1 = Image.open(img1_path)
        img2 = Image.open(img2_path)

        # Resize if needed
        if img1.size != img2.size:
            img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

        w, h = img1.size

        # Create difference image
        arr1 = np.array(img1.convert('RGB'))
        arr2 = np.array(img2.convert('RGB'))

        # Absolute difference
        diff = np.abs(arr1.astype(np.int16) - arr2.astype(np.int16)).astype(np.uint8)

        # Amplify differences for visibility
        diff_amplified = np.clip(diff * 5, 0, 255).astype(np.uint8)

        # Create heatmap
        diff_gray = np.mean(diff, axis=2).astype(np.uint8)

        if HAS_CV2:
            heatmap = cv2.applyColorMap(diff_gray * 5, cv2.COLORMAP_JET)
            heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
            heatmap_img = Image.fromarray(heatmap)
        else:
            # Create heatmap without cv2 using a simple colormap
            heatmap_img = self._create_heatmap_pil(diff_gray * 5)

        # Create composite image (2x2 grid)
        composite_w = w * 2
        composite_h = h * 2
        composite = Image.new('RGB', (composite_w, composite_h), (30, 30, 30))

        # Place images
        composite.paste(img1, (0, 0))
        composite.paste(img2, (w, 0))
        composite.paste(Image.fromarray(diff_amplified), (0, h))
        composite.paste(heatmap_img, (w, h))

        # Add labels
        draw = ImageDraw.Draw(composite)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()

        labels = [
            ("Image 1", 10, 10),
            ("Image 2", w + 10, 10),
            ("Difference (5x)", 10, h + 10),
            ("Heatmap", w + 10, h + 10)
        ]

        for text, x, y in labels:
            # Draw shadow
            draw.text((x+2, y+2), text, fill=(0, 0, 0), font=font)
            # Draw text
            draw.text((x, y), text, fill=(255, 255, 255), font=font)

        composite.save(output_path)
        self.log(f"\nVisual report saved to: {output_path}")

        return output_path

    def _create_heatmap_pil(self, gray_array: np.ndarray) -> Image.Image:
        """Create a heatmap image using PIL (fallback when cv2 not available).

        Args:
            gray_array: Grayscale numpy array (0-255)

        Returns:
            PIL Image with heatmap colors
        """
        # Simple jet-like colormap
        h, w = gray_array.shape
        rgb = np.zeros((h, w, 3), dtype=np.uint8)

        # Normalize to 0-1
        normalized = gray_array.astype(np.float32) / 255.0

        # Blue to Cyan to Green to Yellow to Red
        # Blue (low) -> Cyan -> Green -> Yellow -> Red (high)
        rgb[:, :, 0] = np.clip(4 * normalized - 2, 0, 1) * 255  # Red
        rgb[:, :, 1] = np.clip(np.minimum(4 * normalized, 4 - 4 * normalized), 0, 1) * 255  # Green
        rgb[:, :, 2] = np.clip(2 - 4 * normalized, 0, 1) * 255  # Blue

        return Image.fromarray(rgb)

    def save_report(self, report: FullReport, output_path: str):
        """Save report as JSON.

        Args:
            report: FullReport object
            output_path: Path for JSON file
        """
        # Convert dataclasses to dict
        report_dict = asdict(report)

        with open(output_path, 'w') as f:
            json.dump(report_dict, f, indent=2)

        self.log(f"Report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze two images using deduplication strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s slide1.png slide2.png
  %(prog)s slide1.png slide2.png --output-dir ./analysis
  %(prog)s slide1.png slide2.png --visual --json
        """
    )

    parser.add_argument('image1', help='Path to first image')
    parser.add_argument('image2', help='Path to second image')
    parser.add_argument('--output-dir', '-o', help='Output directory for reports')
    parser.add_argument('--visual', '-v', action='store_true',
                        help='Generate visual difference report')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Save JSON report')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Minimal output')

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.image1):
        print(f"Error: Image not found: {args.image1}")
        sys.exit(1)
    if not os.path.exists(args.image2):
        print(f"Error: Image not found: {args.image2}")
        sys.exit(1)

    # Create output directory if needed
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    # Run analysis
    analyzer = DeduplicationAnalyzer(verbose=not args.quiet)
    report = analyzer.analyze(args.image1, args.image2)

    # Generate outputs
    if args.output_dir:
        base_name = f"dedup_analysis_{int(time.time())}"

        if args.visual:
            visual_path = os.path.join(args.output_dir, f"{base_name}_visual.png")
            analyzer.generate_visual_report(args.image1, args.image2, visual_path)

        if args.json:
            json_path = os.path.join(args.output_dir, f"{base_name}.json")
            analyzer.save_report(report, json_path)
    elif args.visual:
        analyzer.generate_visual_report(args.image1, args.image2, "dedup_visual.png")

    # Return exit code based on verdict
    if "DUPLICATE" in report.overall_verdict:
        sys.exit(0)  # Duplicate
    else:
        sys.exit(1)  # Unique


if __name__ == "__main__":
    main()
