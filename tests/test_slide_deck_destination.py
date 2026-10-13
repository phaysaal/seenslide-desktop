"""Upload Slides window: which cloud session a deck talk lands in.

Regression tests for the "every PDF upload created its own orphan
session" bug — the window now joins the dashboard's current session
unless the presenter picks "new session".
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from gui.windows.slide_deck_window import SlideDeckWindow, _resolve_target_session  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _cloud(created="NEW-0001"):
    cloud = MagicMock()
    cloud.start_session.return_value = created
    cloud.cloud_session_id = None
    cloud.current_talk_id = "stale-talk"
    return cloud


def test_resolve_joins_existing_session_without_creating_one():
    cloud = _cloud()
    sid = _resolve_target_session(cloud, "ABC-1234", "Lecture 5", "Dr. Smith")
    assert sid == "ABC-1234"
    assert cloud.cloud_session_id == "ABC-1234"
    assert cloud.current_talk_id is None, "a stale talk id must not leak into the new talk"
    cloud.start_session.assert_not_called()


def test_resolve_creates_session_named_after_talk_when_no_target():
    cloud = _cloud()
    sid = _resolve_target_session(cloud, None, "Lecture 5", "")
    assert sid == "NEW-0001"
    kwargs = cloud.start_session.call_args.kwargs
    assert kwargs["session_name"] == "Lecture 5"
    assert kwargs["presenter_name"] == "Unknown"


def test_resolve_returns_empty_string_on_failure():
    cloud = _cloud(created="")
    assert _resolve_target_session(cloud, None, "x", "y") == ""


def test_window_defaults_to_current_session(qapp):
    win = SlideDeckWindow(target_session_id="ABC-1234", target_session_name="Physics 101")
    assert win.selected_target_session_id() == "ABC-1234"
    assert "Physics 101" in win._radio_current.text()
    assert "ABC-1234" in win._radio_current.text()
    # Presenter opts out → new session
    win._radio_new.setChecked(True)
    assert win.selected_target_session_id() is None


def test_window_without_current_session_creates_new(qapp):
    win = SlideDeckWindow()
    assert win.selected_target_session_id() is None
    assert not win._radio_current.isVisibleTo(win)
    assert "new session" in win._dest_hint.text().lower()


def test_set_target_session_after_open(qapp):
    win = SlideDeckWindow()
    win.set_target_session("XYZ-9999", "Chemistry")
    assert win.selected_target_session_id() == "XYZ-9999"
    win.set_target_session(None)
    assert win.selected_target_session_id() is None
