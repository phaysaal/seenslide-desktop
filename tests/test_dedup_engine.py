"""Dedup engine: event-bus flow, per-talk reset, title-slide injection.

Covers the two conference-mode guarantees:
  * reset() scopes dedup to the current talk (numbering restarts at 1, a
    later talk's slide is never merged with an earlier talk's);
  * inject_capture() carries a slide in as #1 AND seeds the history so the
    identical on-screen frame isn't stored twice.
"""
import time

import pytest
from PIL import Image, ImageDraw

from core.bus.event_bus import EventBus
from core.interfaces.events import Event, EventType
from core.models.session import Session
from core.models.slide import RawCapture
from modules.dedup.engine import DeduplicationEngine
from modules.dedup.strategies.perceptual_strategy import PerceptualDeduplicationStrategy


def frame(spec):
    """Deterministic frame from a list of rectangles (no font dependency)."""
    im = Image.new("RGB", (640, 400), (250, 250, 252))
    d = ImageDraw.Draw(im)
    for box, color in spec:
        d.rectangle(box, fill=color)
    return im


FRAME_A = [( [40, 40, 300, 120], (0, 128, 128) ), ([60, 200, 500, 240], (20, 20, 20))]
FRAME_B = [( [40, 40, 300, 120], (0, 128, 128) ), ([60, 200, 500, 240], (20, 20, 20)),
           ([60, 300, 480, 340], (20, 20, 20))]
TITLE_FRAME = [( [80, 120, 560, 220], (180, 60, 30) ), ([120, 260, 520, 290], (20, 20, 20))]


@pytest.fixture
def rig():
    bus = EventBus()
    session = Session(name="t")
    strat = PerceptualDeduplicationStrategy()
    strat.initialize({})
    eng = DeduplicationEngine(strategy=strat, session=session, event_bus=bus)
    eng.start()
    uniques = []
    bus.subscribe(EventType.SLIDE_UNIQUE, lambda e: uniques.append(e.data["sequence_number"]))

    def feed(img):
        c = RawCapture(image=img, timestamp=time.time(), monitor_id=0,
                       width=img.width, height=img.height)
        bus.publish(Event(
            type=EventType.SLIDE_CAPTURED,
            data={"session_id": session.session_id, "capture": c,
                  "capture_id": c.capture_id, "timestamp": c.timestamp,
                  "width": c.width, "height": c.height, "monitor_id": 0},
            source="test"))
        return c

    return SimpleRig(eng, feed, uniques)


class SimpleRig:
    def __init__(self, engine, feed, uniques):
        self.engine, self.feed, self.uniques = engine, feed, uniques


def test_unique_then_duplicate_then_unique(rig):
    rig.feed(frame(FRAME_A))
    rig.feed(frame(FRAME_A))          # same content -> duplicate
    rig.feed(frame(FRAME_B))          # revealed line -> unique
    assert rig.uniques == [1, 2]


def test_reset_scopes_dedup_to_current_talk(rig):
    rig.feed(frame(FRAME_A))
    assert rig.uniques == [1]
    rig.engine.reset()
    rig.uniques.clear()
    # The SAME frame in a new talk must be slide 1 again, not a duplicate
    # of the previous talk.
    rig.feed(frame(FRAME_A))
    assert rig.uniques == [1]


def test_inject_carries_slide_and_seeds_history(rig):
    title = frame(TITLE_FRAME)
    cap = RawCapture(image=title, timestamp=time.time(), monitor_id=0,
                     width=title.width, height=title.height)
    rig.engine.inject_capture(cap)
    assert rig.uniques == [1], "injected frame must publish as slide 1"

    rig.feed(title.copy())            # identical frame still on screen
    assert rig.uniques == [1], "seeded history must dedup the same frame"

    rig.feed(frame(FRAME_A))          # presenter advances
    assert rig.uniques == [1, 2]


def test_other_sessions_ignored(rig):
    img = frame(FRAME_A)
    c = RawCapture(image=img, timestamp=time.time(), monitor_id=0,
                   width=img.width, height=img.height)
    rig.engine._event_bus.publish(Event(
        type=EventType.SLIDE_CAPTURED,
        data={"session_id": "some-other-session", "capture": c},
        source="test"))
    assert rig.uniques == []
