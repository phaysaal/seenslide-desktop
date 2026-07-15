"""Upload-outbox drain: failed cloud slide uploads retry and backfill."""
import threading
import time

import pytest
from PIL import Image

from core.models.slide import ProcessedSlide
from modules.storage.manager import StorageManager
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider


class FakeCloud:
    enabled = True
    current_talk_id = "TALK-A"

    def __init__(self):
        self.mode = "down"          # "down" | "404" | "up"
        self.uploads = []
        self.slide_ids_by_number = {}

    def upload_slide_image(self, talk_id, n, data):
        if self.mode == "down":
            return (False, None, None)      # network error
        if self.mode == "404":
            return (False, None, 404)       # talk gone
        self.uploads.append((talk_id, n, len(data)))
        return (True, f"cloud-{n}", 200)


@pytest.fixture
def rig(tmp_path):
    img_path = str(tmp_path / "slide.png")
    Image.new("RGB", (320, 200), (30, 90, 200)).save(img_path)

    db = SQLiteStorageProvider()
    assert db.initialize({"base_path": str(tmp_path)})

    mgr = StorageManager.__new__(StorageManager)
    mgr._database = db
    mgr._config = {"storage": {"jpeg_quality": 60}}
    mgr._cloud = FakeCloud()
    mgr._outbox_stop = threading.Event()

    class Rig:
        pass
    r = Rig()
    r.mgr, r.db, r.cloud, r.img = mgr, db, mgr._cloud, img_path
    yield r
    db.cleanup()


def test_network_down_keeps_rows_and_stops_early(rig):
    rig.db.outbox_add("TALK-A", 1, rig.img, "s")
    rig.db.outbox_add("TALK-A", 2, rig.img, "s")
    rig.mgr._drain_outbox()
    rows = rig.db.outbox_pending()
    assert len(rows) == 2
    # only the first row is attempted before the drain gives up on a
    # network error — the rest would fail too
    assert rows[0]["attempts"] == 1 and rows[1]["attempts"] == 0


def test_recovery_backfills_and_records_ids(rig):
    rig.db.outbox_add("TALK-A", 1, rig.img, "s")
    rig.db.outbox_add("TALK-A", 2, rig.img, "s")
    rig.cloud.mode = "up"
    rig.mgr._drain_outbox()
    assert rig.db.outbox_pending() == []
    assert [(t, n) for t, n, _ in rig.cloud.uploads] == [("TALK-A", 1), ("TALK-A", 2)]
    # cloud slide ids recorded for voice-marker resolution (talk still live)
    assert rig.cloud.slide_ids_by_number == {1: "cloud-1", 2: "cloud-2"}


def test_404_drops_row(rig):
    rig.db.outbox_add("TALK-GONE", 5, rig.img, "s")
    rig.cloud.mode = "404"
    rig.mgr._drain_outbox()
    assert rig.db.outbox_pending() == []


def test_missing_image_drops_row(rig):
    rig.db.outbox_add("TALK-A", 9, "/nonexistent.png", "s")
    rig.cloud.mode = "up"
    rig.mgr._drain_outbox()
    assert rig.db.outbox_pending() == []
    assert rig.cloud.uploads == []


def test_gives_up_after_max_attempts(rig):
    rig.db.outbox_add("TALK-A", 3, rig.img, "s")
    row_id = rig.db.outbox_pending()[0]["id"]
    for _ in range(StorageManager._OUTBOX_MAX_ATTEMPTS):
        rig.db.outbox_bump(row_id)
    rig.cloud.mode = "up"
    rig.mgr._drain_outbox()
    assert rig.db.outbox_pending() == []
    assert rig.cloud.uploads == [], "expired row must not upload"


def test_cloud_disabled_is_noop(rig):
    rig.db.outbox_add("TALK-A", 1, rig.img, "s")
    rig.cloud.enabled = False
    rig.mgr._drain_outbox()
    assert len(rig.db.outbox_pending()) == 1
