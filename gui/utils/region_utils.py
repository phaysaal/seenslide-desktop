"""Utilities for region calculation and validation."""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_default_region(screen_width: int, screen_height: int, percentage: float = 0.5) -> Dict[str, int]:
    """Calculate default centered region as a percentage of screen size.

    Args:
        screen_width: Width of the screen in pixels
        screen_height: Height of the screen in pixels
        percentage: Percentage of screen to use (default: 0.5 for 50%)

    Returns:
        Dictionary with x, y, width, height representing the region

    Example:
        For a 1920x1080 screen with 50% (default):
        Returns: {"x": 480, "y": 270, "width": 960, "height": 540}
    """
    if percentage <= 0 or percentage > 1:
        raise ValueError(f"Percentage must be between 0 and 1, got {percentage}")

    region_width = int(screen_width * percentage)
    region_height = int(screen_height * percentage)

    # Center the region
    x = (screen_width - region_width) // 2
    y = (screen_height - region_height) // 2

    region = {
        "x": x,
        "y": y,
        "width": region_width,
        "height": region_height
    }

    logger.info(
        f"Calculated default region: {percentage*100}% of {screen_width}x{screen_height} "
        f"-> x={x}, y={y}, w={region_width}, h={region_height}"
    )

    return region


def validate_region(
    region: Dict[str, int],
    screen_width: int,
    screen_height: int,
    min_width: int = 100,
    min_height: int = 100
) -> Tuple[bool, Optional[str]]:
    """Validate a crop region.

    Args:
        region: Region dictionary with x, y, width, height
        screen_width: Width of the screen in pixels
        screen_height: Height of the screen in pixels
        min_width: Minimum allowed width (default: 100)
        min_height: Minimum allowed height (default: 100)

    Returns:
        Tuple of (is_valid, error_message)
        If valid: (True, None)
        If invalid: (False, "error description")
    """
    # Check required keys
    required_keys = {"x", "y", "width", "height"}
    if not all(k in region for k in required_keys):
        missing = required_keys - set(region.keys())
        return False, f"Missing required keys: {missing}"

    x = region["x"]
    y = region["y"]
    width = region["width"]
    height = region["height"]

    # Check types and non-negative values
    if not all(isinstance(v, int) for v in [x, y, width, height]):
        return False, "All region values must be integers"

    if x < 0 or y < 0:
        return False, f"Position (x, y) must be non-negative, got ({x}, {y})"

    # Check minimum dimensions
    if width < min_width:
        return False, f"Width must be at least {min_width}px, got {width}px"

    if height < min_height:
        return False, f"Height must be at least {min_height}px, got {height}px"

    # Check region fits within screen bounds
    if x + width > screen_width:
        return False, f"Region extends beyond screen width ({x + width} > {screen_width})"

    if y + height > screen_height:
        return False, f"Region extends beyond screen height ({y + height} > {screen_height})"

    # All checks passed
    logger.debug(f"Region validated successfully: {region}")
    return True, None


def adjust_region_to_bounds(
    region: Dict[str, int],
    screen_width: int,
    screen_height: int
) -> Dict[str, int]:
    """Adjust a region to fit within screen bounds.

    Args:
        region: Region dictionary with x, y, width, height
        screen_width: Width of the screen in pixels
        screen_height: Height of the screen in pixels

    Returns:
        Adjusted region that fits within screen bounds
    """
    x = max(0, region["x"])
    y = max(0, region["y"])
    width = region["width"]
    height = region["height"]

    # Adjust if region extends beyond screen
    if x + width > screen_width:
        # Try to shrink width first
        width = screen_width - x
        # If still too wide, move x
        if width <= 0:
            x = 0
            width = screen_width

    if y + height > screen_height:
        # Try to shrink height first
        height = screen_height - y
        # If still too tall, move y
        if height <= 0:
            y = 0
            height = screen_height

    adjusted = {
        "x": x,
        "y": y,
        "width": width,
        "height": height
    }

    if adjusted != region:
        logger.info(f"Adjusted region from {region} to {adjusted}")

    return adjusted


def region_to_tuple(region: Dict[str, int]) -> Tuple[int, int, int, int]:
    """Convert region dict to tuple (x, y, width, height).

    Args:
        region: Region dictionary

    Returns:
        Tuple of (x, y, width, height)
    """
    return (region["x"], region["y"], region["width"], region["height"])


def tuple_to_region(coords: Tuple[int, int, int, int]) -> Dict[str, int]:
    """Convert tuple to region dict.

    Args:
        coords: Tuple of (x, y, width, height)

    Returns:
        Region dictionary
    """
    return {
        "x": coords[0],
        "y": coords[1],
        "width": coords[2],
        "height": coords[3]
    }


def get_region_info(region: Dict[str, int]) -> str:
    """Get human-readable region information.

    Args:
        region: Region dictionary

    Returns:
        Human-readable string describing the region
    """
    x, y, w, h = region["x"], region["y"], region["width"], region["height"]
    x2 = x + w
    y2 = y + h

    return (
        f"Position: ({x}, {y})\n"
        f"Size: {w}×{h}\n"
        f"Bounds: ({x}, {y}) to ({x2}, {y2})"
    )
