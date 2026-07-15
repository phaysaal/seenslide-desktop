"""load_defaults() must agree with the shipped config.yaml.

The two drifted historically (provider portal-vs-auto, strategy
hash-vs-perceptual), so whichever load path ran gave different behavior.
"""
from pathlib import Path

import yaml

from core.config.config_loader import ConfigLoader

REPO = Path(__file__).resolve().parents[1]


def test_defaults_match_shipped_yaml_on_drift_prone_keys():
    defaults = ConfigLoader().load_defaults()
    shipped = yaml.safe_load((REPO / "config" / "config.yaml").read_text())

    assert defaults["capture"]["provider"] == shipped["capture"]["provider"]
    assert (defaults["deduplication"]["strategy"]
            == shipped["deduplication"]["strategy"])
    assert (defaults["deduplication"]["perceptual_threshold"]
            == shipped["deduplication"]["perceptual_threshold"])
    assert (defaults["storage"]["jpeg_quality"]
            == shipped["storage"]["jpeg_quality"])


def test_defaults_use_auto_provider_and_perceptual():
    d = ConfigLoader().load_defaults()
    assert d["capture"]["provider"] == "auto"
    assert d["deduplication"]["strategy"] == "perceptual"
