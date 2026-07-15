"""SQLite provider: concurrency safety, atomic deletes, upload outbox."""
import threading
import time

import pytest

from core.models.session import Session
from core.models.slide import ProcessedSlide
from modules.storage.providers.sqlite_provider import SQLiteStorageProvider


@pytest.fixture
def db(tmp_path):
    p = SQLiteStorageProvider()
    assert p.initialize({"base_path": str(tmp_path)})
    yield p
    p.cleanup()


def slide(session_id="s", talk_id="T", n=1):
    return ProcessedSlide(session_id=session_id, talk_id=talk_id,
                          sequence_number=n, timestamp=time.time())


def test_wal_mode_enabled(db):
    assert db._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_concurrent_writers_no_errors_no_orphans(db):
    """4 slide writers + 2 talk create/delete threads must interleave safely
    (this failed with 'database is locked' / orphan rows before the write
    lock + WAL)."""
    s = Session(name="conc")
    db.create_session(s)
    errors = []

    def writer(k):
        try:
            for i in range(50):
                db.save_slide(slide(s.session_id, "T", k * 1000 + i))
        except Exception as e:
            errors.append(e)

    def churner():
        try:
            for i in range(20):
                tid = db.create_talk(s.session_id, f"t{i}")
                db.delete_talk(tid)
        except Exception as e:
            errors.append(e)

    threads = ([threading.Thread(target=writer, args=(k,)) for k in range(4)]
               + [threading.Thread(target=churner) for _ in range(2)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert db._conn.execute("SELECT COUNT(*) FROM slides").fetchone()[0] == 200
    assert db._conn.execute("SELECT COUNT(*) FROM talks").fetchone()[0] == 0


def test_write_rolls_back_on_error(db):
    """A failure mid-transaction must not leave half-committed rows."""
    with pytest.raises(RuntimeError):
        with db._write() as cursor:
            cursor.execute(
                "INSERT INTO talks (talk_id, session_id, title, created_at) "
                "VALUES ('roll', 's', 'x', 0)")
            raise RuntimeError("boom")
    assert db._conn.execute(
        "SELECT COUNT(*) FROM talks WHERE talk_id='roll'").fetchone()[0] == 0


def test_delete_session_cascades(db):
    s = Session(name="cascade")
    db.create_session(s)
    tid = db.create_talk(s.session_id, "talk")
    db.save_slide(slide(s.session_id, tid, 1))
    assert db.delete_session(s.session_id)
    for table in ("sessions", "talks", "slides"):
        count = db._conn.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0, f"{table} not cleaned"


# ---------------------------------------------------------------------------
# Upload outbox
# ---------------------------------------------------------------------------

def test_outbox_roundtrip(db):
    db.outbox_add("T", 1, "/img/1.png", "s")
    db.outbox_add("T", 2, "/img/2.png", "s")
    rows = db.outbox_pending()
    assert [(r["talk_id"], r["slide_number"]) for r in rows] == [("T", 1), ("T", 2)]

    db.outbox_bump(rows[0]["id"])
    assert db.outbox_pending()[0]["attempts"] == 1

    db.outbox_remove(rows[0]["id"])
    assert [r["slide_number"] for r in db.outbox_pending()] == [2]


def test_outbox_requeue_replaces_not_duplicates(db):
    db.outbox_add("T", 5, "/img/5.png", "s")
    db.outbox_add("T", 5, "/img/5-new.png", "s")
    rows = db.outbox_pending()
    assert len(rows) == 1
    assert rows[0]["image_path"] == "/img/5-new.png"


def test_outbox_survives_reopen(db, tmp_path):
    db.outbox_add("T", 7, "/img/7.png", "s")
    db.cleanup()
    reopened = SQLiteStorageProvider()
    assert reopened.initialize({"base_path": str(tmp_path)})
    assert [r["slide_number"] for r in reopened.outbox_pending()] == [7]
    reopened.cleanup()


# ---------------------------------------------------------------------------
# Corruption recovery + backup
# ---------------------------------------------------------------------------

def test_backup_written_on_init_and_cleanup(db):
    assert db._backup_path.exists(), "init must write a last-known-good backup"


def test_corrupt_db_restored_from_backup(db, tmp_path):
    """Garbage in seenslide.db must be detected at open and the previous
    backup restored — corruption used to mean total local data loss."""
    s = Session(name="precious")
    db.create_session(s)
    db.save_slide(slide(s.session_id, "T", 1))
    db.cleanup()  # refreshes the backup with this data

    db_file = tmp_path / "db" / "seenslide.db"
    db_file.write_bytes(b"this is not a sqlite database" * 1000)

    recovered = SQLiteStorageProvider()
    assert recovered.initialize({"base_path": str(tmp_path)})
    names = [r["name"] for r in recovered._conn.execute("SELECT name FROM sessions")]
    assert names == ["precious"], "backup data must survive corruption"
    # the corrupt file is kept aside for forensics
    assert list((tmp_path / "db").glob("*.corrupt-*")), "corrupt db must be preserved"
    recovered.cleanup()


def test_corrupt_db_without_backup_starts_fresh(tmp_path):
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True)
    (db_dir / "seenslide.db").write_bytes(b"garbage" * 5000)

    p = SQLiteStorageProvider()
    assert p.initialize({"base_path": str(tmp_path)})
    assert p._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    p.cleanup()
