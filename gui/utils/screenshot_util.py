"""Screenshot utilities using MSS library."""

from typing import Optional, Tuple, Dict, List
import logging
from PIL import Image
import mss

logger = logging.getLogger(__name__)


def get_screen_info() -> List[Dict[str, int]]:
    """Get information about all available screens.

    Returns:
        List of dictionaries containing screen information:
        [
            {"id": 0, "left": 0, "top": 0, "width": 1920, "height": 1080},
            ...
        ]
    """
    with mss.mss() as sct:
        monitors = sct.monitors
        screens = []

        # monitors[0] is all monitors combined, skip it
        for i, monitor in enumerate(monitors[1:], start=1):
            screen = {
                "id": i,
                "left": monitor["left"],
                "top": monitor["top"],
                "width": monitor["width"],
                "height": monitor["height"]
            }
            screens.append(screen)
            logger.debug(f"Monitor {i}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})")

        return screens


def get_primary_screen_size() -> Tuple[int, int]:
    """Get the size of the primary screen.

    Returns:
        Tuple of (width, height) in pixels
    """
    with mss.mss() as sct:
        # Monitor 1 is typically the primary monitor
        monitor = sct.monitors[1]
        return (monitor["width"], monitor["height"])


def capture_screenshot(monitor_id: int = 1) -> Optional[Image.Image]:
    """Capture screenshot of specified monitor.

    Args:
        monitor_id: Monitor to capture (1 = primary, 2 = secondary, etc.)

    Returns:
        PIL Image object, or None if capture failed
    """
    try:
        with mss.mss() as sct:
            # Validate monitor ID
            if monitor_id < 1 or monitor_id >= len(sct.monitors):
                logger.error(f"Invalid monitor ID: {monitor_id}. Available: 1-{len(sct.monitors)-1}")
                monitor_id = 1  # Fallback to primary

            # Capture screenshot
            monitor = sct.monitors[monitor_id]
            sct_img = sct.grab(monitor)

            # Convert to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            logger.info(f"Screenshot captured from monitor {monitor_id}: {img.width}x{img.height}")
            return img

    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")
        return None


def capture_region(
    x: int,
    y: int,
    width: int,
    height: int,
    monitor_id: int = 1
) -> Optional[Image.Image]:
    """Capture screenshot of a specific region.

    Args:
        x: Left position in pixels
        y: Top position in pixels
        width: Width in pixels
        height: Height in pixels
        monitor_id: Monitor to capture from (default: 1 for primary)

    Returns:
        PIL Image object, or None if capture failed
    """
    try:
        with mss.mss() as sct:
            # Get monitor offset
            monitor = sct.monitors[monitor_id]
            monitor_left = monitor["left"]
            monitor_top = monitor["top"]

            # Define region relative to monitor
            region = {
                "left": monitor_left + x,
                "top": monitor_top + y,
                "width": width,
                "height": height
            }

            # Capture region
            sct_img = sct.grab(region)

            # Convert to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            logger.info(f"Region captured: {width}x{height} at ({x}, {y})")
            return img

    except Exception as e:
        logger.error(f"Failed to capture region: {e}")
        return None


def save_screenshot(
    output_path: str,
    monitor_id: int = 1,
    quality: int = 95
) -> bool:
    """Capture and save screenshot to file.

    Args:
        output_path: Path to save image file
        monitor_id: Monitor to capture (default: 1 for primary)
        quality: JPEG quality if saving as JPEG (default: 95)

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        img = capture_screenshot(monitor_id)
        if img is None:
            return False

        # Save image
        if output_path.lower().endswith('.jpg') or output_path.lower().endswith('.jpeg'):
            img.save(output_path, "JPEG", quality=quality)
        else:
            img.save(output_path)

        logger.info(f"Screenshot saved to: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to save screenshot: {e}")
        return False


def get_monitor_count() -> int:
    """Get the number of available monitors.

    Returns:
        Number of monitors
    """
    with mss.mss() as sct:
        # monitors[0] is all monitors combined, so subtract 1
        return len(sct.monitors) - 1


def get_all_screens_combined_size() -> Tuple[int, int]:
    """Get the combined size of all screens.

    Returns:
        Tuple of (width, height) covering all monitors
    """
    with mss.mss() as sct:
        # Monitor 0 represents all monitors combined
        monitor = sct.monitors[0]
        return (monitor["width"], monitor["height"])
