"""OCR + fuzzy matching of slide text against a scheduled talk.

Conference mode uses this to auto-advance: when the on-screen slide is the
title slide of the NEXT scheduled talk, the current talk ends and the next
one starts automatically. The matching is deliberately forgiving because the
inputs are messy on both sides:

  * the OCR side — recognition errors, hyphenation, decorations;
  * the schedule side — a title that spans 2–3 lines on the slide, and a
    presenter who is just one name inside a multi-author list.

So we normalize everything to a flat lowercase token stream (which collapses
line breaks — a 3-line title becomes the same tokens as a 1-line one) and ask
two questions:

  1. TITLE:     what fraction of the title's significant tokens appear in the
                slide text (fuzzy per-token, so "Fixpoint"~"Fixpo1nt" counts)?
  2. PRESENTER: do the presenter's name tokens appear (fuzzy) anywhere — e.g.
                inside "M. F. Al Ameen, N. Kobayashi, R. Sato"?

Decision: title coverage ≥ 0.75 AND presenter found (when the schedule row
has one); title-only rows need ≥ 0.9 to compensate. An agenda slide listing
all talks is the classic false-positive — requiring the presenter line too
makes that much less likely to fire.

OCR engines, tried in order (both optional; without either the feature is
reported unavailable and conference mode stays manual):
  * pytesseract  — thin wrapper, needs the system `tesseract` binary
  * rapidocr-onnxruntime — pip-only, bundled models, no system dependency
"""
import logging
import re
import threading
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tokens too generic to count as evidence for a *specific* talk title.
_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "over", "under", "about",
    "of", "in", "on", "at", "to", "a", "an", "by", "via", "using", "towards",
    "toward", "new", "based",
}

_TITLE_THRESHOLD = 0.75          # with presenter confirmation
_TITLE_ONLY_THRESHOLD = 0.90     # no presenter in the schedule row
_TOKEN_FUZZ = 0.8                # per-token similarity to survive OCR noise


# --------------------------------------------------------------------------- #
# OCR engines (lazy, cached, optional)
# --------------------------------------------------------------------------- #

_engine = None            # ("tesseract" | "rapidocr", callable) once resolved
_engine_lock = threading.Lock()
_engine_resolved = False


def _resolve_engine():
    global _engine, _engine_resolved
    with _engine_lock:
        if _engine_resolved:
            return _engine

        # 1. pytesseract + system binary
        try:
            import shutil
            import pytesseract
            if shutil.which("tesseract"):
                def _tess(image):
                    return pytesseract.image_to_string(image)
                _engine = ("tesseract", _tess)
        except Exception:
            pass

        # 2. RapidOCR (pip-only, bundled models)
        if _engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                import numpy as np
                ocr = RapidOCR()

                def _rapid(image):
                    result, _ = ocr(np.asarray(image.convert("RGB")))
                    if not result:
                        return ""
                    return "\n".join(line[1] for line in result)
                _engine = ("rapidocr", _rapid)
            except Exception:
                pass

        _engine_resolved = True
        if _engine:
            logger.info(f"Slide OCR engine: {_engine[0]}")
        else:
            logger.info(
                "No OCR engine available (install tesseract-ocr or "
                "rapidocr-onnxruntime) — title auto-advance disabled"
            )
        return _engine


def ocr_available() -> bool:
    return _resolve_engine() is not None


def extract_text(image) -> str:
    """OCR a PIL image → raw text. Fail-safe: returns "" on any problem."""
    engine = _resolve_engine()
    if engine is None:
        return ""
    try:
        # Downscale very large captures — OCR quality doesn't need 4K and
        # the models get slow. ~1600px wide keeps slide text crisp.
        w, h = image.size
        if w > 1600:
            image = image.resize((1600, int(h * 1600 / w)))
        return engine[1](image) or ""
    except Exception as e:
        logger.debug(f"OCR failed ({e})")
        return ""


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #

def _tokens(text: str) -> List[str]:
    """Normalized token stream: lowercase, punctuation stripped, line breaks
    collapsed (so a multi-line title equals its single-line form)."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _significant(tokens: List[str]) -> List[str]:
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _token_present(token: str, haystack: List[str]) -> bool:
    """Fuzzy membership — survives OCR errors like 'flxpoint'/'fixpoint'."""
    for h in haystack:
        if token == h:
            return True
        # Cheap length gate before the expensive ratio
        if abs(len(h) - len(token)) <= 2 and len(token) >= 4:
            if SequenceMatcher(None, token, h).ratio() >= _TOKEN_FUZZ:
                return True
    return False


def title_score(slide_text: str, title: str) -> float:
    """Fraction of the title's significant tokens found in the slide text."""
    title_tokens = _significant(_tokens(title))
    if not title_tokens:
        return 0.0
    slide_tokens = _tokens(slide_text)
    hits = sum(1 for t in title_tokens if _token_present(t, slide_tokens))
    return hits / len(title_tokens)


def presenter_found(slide_text: str, presenter: str) -> bool:
    """True if the presenter's name tokens appear (fuzzy) in the slide text.

    Only name-shaped tokens count (len ≥ 3 — skips initials like "M."), and a
    majority of them must be present, so "Naoki Kobayashi" matches inside a
    full author list while a single shared surname alone doesn't fire.
    """
    name_tokens = [t for t in _tokens(presenter) if len(t) >= 3]
    if not name_tokens:
        return False
    slide_tokens = _tokens(slide_text)
    hits = sum(1 for t in name_tokens if _token_present(t, slide_tokens))
    return hits / len(name_tokens) >= 0.5 and hits >= 1


def matches_talk(slide_text: str, title: str,
                 presenter: str = "") -> Tuple[bool, float]:
    """Is this slide the title slide of the scheduled talk?

    Returns (matched, title_score). With a presenter in the schedule, both
    the title and the presenter must be found; without one, the title alone
    must match near-perfectly.
    """
    if not slide_text or not title:
        return False, 0.0
    score = title_score(slide_text, title)
    if presenter.strip():
        return (score >= _TITLE_THRESHOLD
                and presenter_found(slide_text, presenter)), score
    return score >= _TITLE_ONLY_THRESHOLD, score
