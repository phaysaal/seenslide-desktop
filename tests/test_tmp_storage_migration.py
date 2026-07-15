"""Legacy /tmp/seenslide data must be rescued to the persistent location.

Older configs used `base_dir` (a key nothing read), so slides and the DB
landed in the providers' volatile /tmp/seenslide fallback and vanished on
reboot. StorageManager._migrate_tmp_storage moves that data to the default
base path once — and must never touch custom base paths (the GUI-test
sandbox) or overwrite an existing target DB.
"""
import sqlite3
from pathlib import Path

import pytest

from modules.storage.manager import StorageManager


@pytest.fixture
def fake_homes(tmp_path, monkeypatch):
    """Isolated 'home' and '/tmp/seenslide' both inside tmp_path."""
    home = tmp_path / "home"
    legacy = tmp_path / "tmp-seenslide"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

    def make_legacy():
        (legacy / "db").mkdir(parents=True)
        conn = sqlite3.connect(legacy / "db" / "seenslide.db")
        conn.execute("CREATE TABLE slides (image_path TEXT, thumbnail_path TEXT)")
        conn.execute("INSERT INTO slides VALUES (?, ?)",
                     (f"{legacy}/images/slide_1.png",
                      f"{legacy}/thumbnails/thumb_1.png"))
        conn.commit()
        conn.close()
        (legacy / "images").mkdir()
        (legacy / "images" / "slide_1.png").write_bytes(b"png")
        return legacy

    return home, legacy, make_legacy


def test_migrates_default_path(fake_homes, monkeypatch):
    home, legacy, make_legacy = fake_homes
    make_legacy()
    monkeypatch.setattr(StorageManager, "_LEGACY_TMP", str(legacy))
    StorageManager._migrate_tmp_storage({})

    base = home / ".local" / "share" / "seenslide"
    assert (base / "db" / "seenslide.db").exists()
    assert (base / "images" / "slide_1.png").exists()
    assert not (legacy / "db").exists()

    conn = sqlite3.connect(base / "db" / "seenslide.db")
    row = conn.execute("SELECT image_path FROM slides").fetchone()
    conn.close()
    assert row[0] == f"{base}/images/slide_1.png"


def test_custom_base_path_never_migrates(fake_homes, tmp_path, monkeypatch):
    home, legacy, make_legacy = fake_homes
    make_legacy()
    monkeypatch.setattr(StorageManager, "_LEGACY_TMP", str(legacy))
    custom = tmp_path / "sandbox-data"
    StorageManager._migrate_tmp_storage({"base_path": str(custom)})

    # legacy data untouched, nothing created in the custom path
    assert (legacy / "db" / "seenslide.db").exists()
    assert not custom.exists()


def test_existing_target_never_overwritten(fake_homes, monkeypatch):
    home, legacy, make_legacy = fake_homes
    make_legacy()
    monkeypatch.setattr(StorageManager, "_LEGACY_TMP", str(legacy))
    base = home / ".local" / "share" / "seenslide"
    (base / "db").mkdir(parents=True)
    (base / "db" / "seenslide.db").write_bytes(b"current data")

    StorageManager._migrate_tmp_storage({})

    assert (base / "db" / "seenslide.db").read_bytes() == b"current data"
    assert (legacy / "db" / "seenslide.db").exists()
