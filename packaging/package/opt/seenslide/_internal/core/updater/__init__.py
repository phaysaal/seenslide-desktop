"""Auto-update and messaging system for SeenSlide."""

from .update_checker import UpdateChecker
from .downloader import UpdateDownloader

__all__ = ['UpdateChecker', 'UpdateDownloader']
