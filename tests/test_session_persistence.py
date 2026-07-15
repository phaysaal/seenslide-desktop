"""update_session must PERSIST the session row, not just update references.

Regression test for a bug found by the GUI harness (P4 unhide scenario):
cloud_session_id was set on the in-memory session when the user picked a
collection, the lazy local-row switch then saw values already equal and
skipped, and orchestrator.update_session never wrote the row — so the DB
kept cloud_session_id=NULL and the Sessions detail view showed
"No talks found" for perfectly good talks.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from seenslide.orchestrator import SeenSlideOrchestrator


def test_update_session_persists_row():
    orch = SeenSlideOrchestrator()
    orch._running = True
    orch.session = SimpleNamespace(session_id="old")
    orch.storage_manager = MagicMock()
    orch.capture_daemon = None
    orch.dedup_engine = None

    new = SimpleNamespace(
        session_id="local-1", cloud_session_id="ABC-1234",
        name="Talk", presenter_name="P", description="")
    assert orch.update_session(new, create_talk=False) is True

    orch.storage_manager._database.update_session.assert_called_once_with(new)


def test_update_session_survives_persist_failure():
    orch = SeenSlideOrchestrator()
    orch._running = True
    orch.session = SimpleNamespace(session_id="old")
    orch.storage_manager = MagicMock()
    orch.storage_manager._database.update_session.side_effect = RuntimeError("disk")
    orch.capture_daemon = None
    orch.dedup_engine = None

    new = SimpleNamespace(
        session_id="local-1", cloud_session_id="ABC-1234",
        name="Talk", presenter_name="P", description="")
    # a failed persist must not abort the talk-start flow
    assert orch.update_session(new, create_talk=False) is True
