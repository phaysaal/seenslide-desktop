"""Perceptual dedup strategy: fingerprints + tiled localized-change detection.

The tiled diff exists because a global dhash averages away a single revealed
line on a slide (real bug: incremental Beamer reveals merged as duplicates).
Synthetic frames use geometric shapes, not text, so no font dependency.
"""
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from modules.dedup.strategies.perceptual_strategy import PerceptualDeduplicationStrategy


@pytest.fixture
def strategy():
    s = PerceptualDeduplicationStrategy()
    assert s.initialize({})
    return s


def base_slide():
    """A slide-like frame with real structure (title bar + content blocks)."""
    im = Image.new("RGB", (1600, 1000), (250, 250, 252))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 60, 1600, 160], fill=(0, 128, 128))       # title band
    d.rectangle([200, 300, 900, 340], fill=(30, 30, 30))       # text line 1
    d.rectangle([200, 400, 1100, 440], fill=(30, 30, 30))      # text line 2
    return im


def fp(strategy, img):
    return strategy.fingerprint(SimpleNamespace(image=img))


def verdict(strategy, a, b):
    dup = strategy.compare_fingerprints(fp(strategy, a), fp(strategy, b))
    return dup, strategy.get_similarity_score()


def test_identical_frames_are_duplicates(strategy):
    a = base_slide()
    dup, sim = verdict(strategy, a, a.copy())
    assert dup and sim == 1.0


def test_single_added_line_is_unique(strategy):
    """One new text-line-sized block must force a NEW slide even though the
    global hash barely moves."""
    a = base_slide()
    b = base_slide()
    ImageDraw.Draw(b).rectangle([200, 820, 950, 850], fill=(30, 30, 30))
    dup, _ = verdict(strategy, a, b)
    assert not dup, "a revealed line must not be merged as a duplicate"


def test_minor_noise_stays_duplicate(strategy):
    """Compression-level noise must NOT split a slide in two."""
    import io
    a = base_slide()
    buf = io.BytesIO()
    a.save(buf, "JPEG", quality=70)
    b = Image.open(buf).convert("RGB")
    dup, _ = verdict(strategy, a, b)
    assert dup, "JPEG recompression noise must stay a duplicate"


def test_different_slides_are_unique(strategy):
    a = base_slide()
    b = Image.new("RGB", (1600, 1000), (250, 250, 252))
    d = ImageDraw.Draw(b)
    d.rectangle([100, 100, 700, 500], fill=(180, 40, 40))
    d.rectangle([900, 600, 1500, 900], fill=(40, 40, 180))
    dup, sim = verdict(strategy, a, b)
    assert not dup and sim < 0.95


def test_fingerprint_is_compact(strategy):
    """The fingerprint must stay small — storing full frames per slide caused
    the historical ~2GB memory growth."""
    f = fp(strategy, base_slide())
    assert set(f.keys()) == {"dhash", "thumb"}
    assert f["thumb"].nbytes < 64 * 1024


def test_legacy_is_duplicate_still_works(strategy):
    a = SimpleNamespace(image=base_slide())
    assert strategy.is_duplicate(a, SimpleNamespace(image=base_slide()))
