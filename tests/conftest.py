"""Pytest bootstrap: make the project root importable.

Tests import project code as top-level packages (core.*, modules.*,
seenslide.*), exactly like the application does.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
