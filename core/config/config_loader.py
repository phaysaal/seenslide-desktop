"""Configuration loading and management."""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exception raised when configuration is invalid."""
    pass


class ConfigLoader:
    """Configuration loader for SeenSlide."""

    def __init__(self):
        """Initialize the config loader."""
        self.config: Optional[Dict[str, Any]] = None

    def load_from_file(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file.

        Args:
            config_path: Path to config file

        Returns:
            Dictionary containing configuration

        Raises:
            ConfigurationError: If config file not found or invalid
        """
        path = Path(config_path)

        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")

        logger.info(f"Loading configuration from: {path}")

        # Load YAML
        try:
            with open(path, 'r') as f:
                self.config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error reading config file: {e}")

        logger.info("Configuration loaded successfully")
        return self.config

    def load_defaults(self) -> Dict[str, Any]:
        """Load default configuration.

        Returns:
            Dictionary containing default configuration
        """
        self.config = {
            "capture": {
                "provider": "mss",
                "interval_seconds": 2.0,
                "save_raw": False
            },
            "deduplication": {
                "strategy": "hash",
                "hash_algorithm": "md5",
                "perceptual_threshold": 0.90
            },
            "storage": {
                "provider": "sqlite",
                "base_path": "/tmp/seenslide",
                "images_subdir": "images",
                "thumbnails_subdir": "thumbnails",
                "database_subdir": "db",
                "database_filename": "seenslide.db",
                "create_thumbnails": True,
                "thumbnail_width": 320,
                "thumbnail_quality": 85
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8000
            }
        }

        logger.info("Loaded default configuration")
        return self.config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Configuration key (dot-separated for nested keys)
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if not self.config:
            return default

        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def save_to_file(self, config_path: str) -> None:
        """Save configuration to YAML file.

        Args:
            config_path: Path where to save the config

        Raises:
            ConfigurationError: If save fails
        """
        if not self.config:
            raise ConfigurationError("No configuration loaded")

        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Configuration saved to: {path}")
        except Exception as e:
            raise ConfigurationError(f"Error saving config file: {e}")
