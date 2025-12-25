"""Capture mode definitions."""

from enum import Enum


class CaptureMode(Enum):
    """Capture mode for screen capture.

    IDLE: Low-frequency capture to keep portal session alive, don't save slides
    ACTIVE: Normal capture rate, save slides
    """
    IDLE = "idle"
    ACTIVE = "active"
