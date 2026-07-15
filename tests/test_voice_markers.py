"""Voice slide-markers must be recorded for LOCAL-ONLY recordings too.

Regression test for a bug found by the GUI harness (P2 voice scenario):
the SLIDE_UNIQUE -> add_marker subscription only happened inside the cloud
branch of start_voice_recording(), so a recording made with cloud disabled
produced a WAV with 0 markers — impossible to sync to slides afterwards.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.interfaces.events import EventType
from seenslide.orchestrator import SeenSlideOrchestrator


def _start_local_recording(orch):
    """Drive start_voice_recording with a mocked local recorder, no cloud."""
    orch._voice_enabled = True
    orch._running = True
    orch.session = SimpleNamespace(session_id="s1")
    orch.storage_manager = None          # cloud path unreachable
    orch.capture_daemon = None
    recorder = MagicMock()
    recorder.start.return_value = True
    recorder.markers = []
    def _add(**kw):
        ts = kw.get("timestamp_seconds")
        recorder.markers.append(SimpleNamespace(
            slide_number=kw.get("slide_number"),
            timestamp_seconds=1.0 if ts is None else ts))
    recorder.add_marker.side_effect = _add
    with patch("seenslide.orchestrator.VoiceRecorder", return_value=recorder):
        assert orch.start_voice_recording() is True
    return recorder


def _publish_unique(orch, sequence_number):
    from core.bus.event_bus import Event
    orch.event_bus.publish(Event(
        EventType.SLIDE_UNIQUE,
        data={"sequence_number": sequence_number, "capture": None},
        source="test"))


def test_local_only_recording_gets_slide_markers():
    orch = SeenSlideOrchestrator()
    recorder = _start_local_recording(orch)

    _publish_unique(orch, 1)
    _publish_unique(orch, 2)

    assert [m.slide_number for m in recorder.markers] == [1, 2]
    # first marker is anchored to the start of the recording
    assert recorder.markers[0].timestamp_seconds == 0.0


def test_local_only_recording_does_not_grow_cloud_flush_queue():
    orch = SeenSlideOrchestrator()
    _start_local_recording(orch)

    for n in range(1, 6):
        _publish_unique(orch, n)

    # no cloud uploader -> nothing queued for upload
    assert len(orch._pending_voice_markers) == 0
