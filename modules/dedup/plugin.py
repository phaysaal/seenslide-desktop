"""Deduplication module plugin registration."""

import logging
from core.registry.plugin_registry import PluginRegistry
from modules.dedup.strategies.hash_strategy import HashDeduplicationStrategy
from modules.dedup.strategies.perceptual_strategy import PerceptualDeduplicationStrategy
from modules.dedup.strategies.hybrid_strategy import HybridDeduplicationStrategy

logger = logging.getLogger(__name__)


def register():
    """Register all deduplication strategies with the plugin registry."""
    registry = PluginRegistry()

    # Register all strategies
    registry.register_dedup_strategy("hash", HashDeduplicationStrategy)
    registry.register_dedup_strategy("perceptual", PerceptualDeduplicationStrategy)
    registry.register_dedup_strategy("hybrid", HybridDeduplicationStrategy)

    logger.debug("Deduplication strategies registered")


# Auto-register on import
register()
