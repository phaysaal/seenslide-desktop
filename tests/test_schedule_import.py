"""CSV/text talk-schedule parser — the 8 file shapes organizers produce."""
import pytest

from modules.slides.schedule_import import parse_talk_csv


@pytest.fixture
def write(tmp_path):
    def _write(content, name="sched.csv", encoding="utf-8"):
        p = tmp_path / name
        p.write_text(content, encoding=encoding)
        return str(p)
    return _write


def test_plain_comma(write):
    p = write("Fixpoint Logic,Faisal\nSecond Talk,Naoki Kobayashi\n")
    assert parse_talk_csv(p) == [
        ("Fixpoint Logic", "Faisal"), ("Second Talk", "Naoki Kobayashi")]


def test_header_reversed_columns(write):
    p = write("Speaker,Title\nFaisal,Fixpoint Logic\nKobayashi,Second Talk\n")
    assert parse_talk_csv(p) == [
        ("Fixpoint Logic", "Faisal"), ("Second Talk", "Kobayashi")]


def test_semicolon_blank_lines_extra_columns(write):
    p = write("Talk One;Alice;09:00\n\nTalk Two;Bob;10:00\n")
    assert parse_talk_csv(p) == [("Talk One", "Alice"), ("Talk Two", "Bob")]


def test_tab_separated(write):
    p = write("Talk A\tSpeaker A\nTalk B\tSpeaker B\n", name="sched.tsv")
    assert parse_talk_csv(p) == [("Talk A", "Speaker A"), ("Talk B", "Speaker B")]


def test_title_only_lines(write):
    p = write("Just A Title\nAnother Title\n", name="sched.txt")
    assert parse_talk_csv(p) == [("Just A Title", ""), ("Another Title", "")]


def test_quoted_commas_inside_title(write):
    p = write('"Logic, Proofs, and Programs",Carol\n')
    assert parse_talk_csv(p) == [("Logic, Proofs, and Programs", "Carol")]


def test_utf8_bom_with_header(write):
    p = write("﻿Title,Presenter\nBOM Talk,Dave\n")
    assert parse_talk_csv(p) == [("BOM Talk", "Dave")]


def test_missing_title_becomes_talk_n(write):
    p = write(",Eve\nReal Title,Frank\n")
    assert parse_talk_csv(p) == [("Talk 1", "Eve"), ("Real Title", "Frank")]


def test_empty_file(write):
    p = write("")
    assert parse_talk_csv(p) == []


def test_latin1_fallback(write, tmp_path):
    p = tmp_path / "latin.csv"
    p.write_bytes("Caf\xe9 Talk,Ren\xe9\n".encode("latin-1"))
    assert parse_talk_csv(str(p)) == [("Café Talk", "René")]
