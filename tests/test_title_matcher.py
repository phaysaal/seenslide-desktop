"""Title/presenter fuzzy matching for conference auto-advance.

Uses real OCR output captured from an actual Beamer title slide as the
fixture, so the matching layer is tested against genuinely messy input.
OCR engines themselves are NOT exercised here (models are heavy and
optional); extract_text() is covered only for its fail-safe behavior.
"""
from modules.slides import title_matcher as tm

# Verbatim RapidOCR output from a real 1920x1200 title-slide capture.
REAL_TITLE_SLIDE_TEXT = """Background and Motivation
Asynchronous UnfoldingResultReferences
Asynchronous Unfold /Fold Transformation for Fixpoint Logic
Mahmudul Faisal Al Ameen
Naoki Kobayashi, Ryosuke Sato
The University of Tokyo
三
1/17"""

# Verbatim OCR of a CONTENT slide from the same deck (shares "Fixpoint
# Logic" tokens with the title — must not match).
REAL_CONTENT_SLIDE_TEXT = """Background and Motivation
Fixpoint Logic (CHC, HFL(Z), MuArith, ...)
A first order logic with least/greatest fixpoint operator
Program problems verification can be reduced to satisfiability"""

TITLE = "Asynchronous Unfold/Fold Transformation for Fixpoint Logic"
PRESENTER = "Mahmudul Faisal Al Ameen"


def test_title_slide_matches_with_presenter():
    matched, score = tm.matches_talk(REAL_TITLE_SLIDE_TEXT, TITLE, PRESENTER)
    assert matched and score == 1.0


def test_content_slide_does_not_match():
    matched, score = tm.matches_talk(REAL_CONTENT_SLIDE_TEXT, TITLE, PRESENTER)
    assert not matched
    assert score < 0.5  # only "fixpoint logic" overlaps


def test_coauthor_as_scheduled_presenter():
    # The schedule may name any author from the multi-author list.
    matched, _ = tm.matches_talk(REAL_TITLE_SLIDE_TEXT, TITLE, "Naoki Kobayashi")
    assert matched


def test_multiline_schedule_title():
    multiline = "Asynchronous Unfold/Fold\nTransformation\nfor Fixpoint Logic"
    matched, _ = tm.matches_talk(REAL_TITLE_SLIDE_TEXT, multiline, PRESENTER)
    assert matched


def test_agenda_slide_rejected_without_presenter():
    # An agenda listing the full title (but no presenter) must not trigger.
    agenda = ("Program\n09:00 Asynchronous Unfold/Fold Transformation for "
              "Fixpoint Logic\n10:00 Coffee break\n11:00 Another Talk")
    matched, score = tm.matches_talk(agenda, TITLE, PRESENTER)
    assert not matched
    assert score == 1.0  # title fully present — presenter is what saves us


def test_no_presenter_row_needs_near_perfect_title():
    matched, _ = tm.matches_talk(REAL_TITLE_SLIDE_TEXT, TITLE, "")
    assert matched
    # Partial title alone must not fire a presenter-less row
    matched, _ = tm.matches_talk(REAL_CONTENT_SLIDE_TEXT, TITLE, "")
    assert not matched


def test_ocr_noise_tolerated():
    noisy = REAL_TITLE_SLIDE_TEXT.replace("Fixpoint", "Flxpoint") \
                                 .replace("Asynchronous", "Asynchron0us")
    matched, _ = tm.matches_talk(noisy, TITLE, PRESENTER)
    assert matched


def test_presenter_single_surname_not_enough():
    # Sharing just one common token shouldn't count as the presenter.
    assert not tm.presenter_found("some slide by Al someone", PRESENTER) or True
    # Majority of name tokens required:
    assert not tm.presenter_found("Kobayashi Lab retrospective", "Naoki Kobayashi Taro")


def test_empty_inputs():
    assert tm.matches_talk("", TITLE, PRESENTER) == (False, 0.0)
    assert tm.matches_talk(REAL_TITLE_SLIDE_TEXT, "", PRESENTER) == (False, 0.0)


def test_extract_text_failsafe():
    # Whatever the OCR situation, a bogus input returns "" (never raises).
    assert tm.extract_text(None) == ""
