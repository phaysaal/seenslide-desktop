"""Configuration data models."""

from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class CaptureConfig:
    """Configuration for capture module."""
    provider: str = "mss"
    monitor_id: int = 1
    quality: int = 90
    format: str = "png"
    capture_cursor: bool = False


@dataclass
class DeduplicationConfig:
    """Configuration for deduplication module."""
    strategy: str = "hash"
    hash_algorithm: str = "md5"
    perceptual_threshold: float = 0.95
    perceptual_hash_size: int = 8


@dataclass
class StorageConfig:
    """Configuration for storage module."""
    provider: str = "filesystem"
    base_path: str = "/tmp/seenslide"
    images_subdir: str = "images"
    thumbnails_subdir: str = "thumbnails"
    database_subdir: str = "db"
    create_thumbnails: bool = True
    thumbnail_width: int = 320
    thumbnail_quality: int = 85
    database_type: str = "sqlite"
    database_filename: str = "seenslide.db"


@dataclass
class ServerConfig:
    """Configuration for web server module."""
    host: str = "0.0.0.0"
    port: int = 8080
    enable_cors: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    websocket_enabled: bool = True
    websocket_path: str = "/ws"
    api_prefix: str = "/api/v1"


@dataclass
class AdminConfig:
    """Configuration for admin GUI module."""
    theme: str = "dark"
    color_theme: str = "blue"
    window_width: int = 800
    window_height: int = 600
    window_resizable: bool = True


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    level: str = "INFO"
    log_to_file: bool = True
    log_file: str = "/tmp/seenslide/logs/seenslide.log"
    log_to_console: bool = True
    console_colors: bool = True


@dataclass
class SeenSlideConfig:
    """Complete SeenSlide configuration."""
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
