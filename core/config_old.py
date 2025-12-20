"""Configuration loading and management."""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exception raised when configuration is invalid."""
    pass


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, searches in order:
                    1. ./config/default.yaml
                    2. ~/.seenslide/config.yaml

    Returns:
        Dictionary containing configuration

    Raises:
        ConfigurationError: If config file not found or invalid
    """
    # Determine config file path
    if config_path:
        path = Path(config_path)
    else:
        # Try default locations
        default_paths = [
            Path("config/default.yaml"),
            Path.home() / ".seenslide" / "config.yaml",
        ]
        path = None
        for p in default_paths:
            if p.exists():
                path = p
                break

        if path is None:
            raise ConfigurationError(
                "Config file not found. Searched: " +
                ", ".join(str(p) for p in default_paths)
            )

    logger.info(f"Loading configuration from: {path}")

    # Load YAML
    try:
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        raise ConfigurationError(f"Error reading config file: {e}")

    # Validate configuration
    validate_config(config)

    logger.info("Configuration loaded successfully")
    return config


def validate_config(config: Dict[str, Any]) -> None:
    """Validate configuration has required fields.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ConfigurationError: If configuration is invalid
    """
    required_sections = ['capture', 'deduplication', 'storage', 'server']
    for section in required_sections:
        if section not in config:
            raise ConfigurationError(f"Missing required config section: {section}")

    # Validate capture config
    if 'provider' not in config['capture']:
        raise ConfigurationError("Missing 'provider' in capture config")

    # Validate deduplication config
    if 'strategy' not in config['deduplication']:
        raise ConfigurationError("Missing 'strategy' in deduplication config")

    # Validate storage config
    if 'provider' not in config['storage']:
        raise ConfigurationError("Missing 'provider' in storage config")
    if 'base_path' not in config['storage'].get('config', {}):
        raise ConfigurationError("Missing 'base_path' in storage config")

    # Validate server config
    if 'port' not in config['server']:
        raise ConfigurationError("Missing 'port' in server config")

    logger.debug("Configuration validation passed")


def save_config(config: Dict[str, Any], config_path: str) -> None:
    """Save configuration to YAML file.

    Args:
        config: Configuration dictionary
        config_path: Path where to save the config

    Raises:
        ConfigurationError: If save fails
    """
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Configuration saved to: {path}")
    except Exception as e:
        raise ConfigurationError(f"Error saving config file: {e}")
