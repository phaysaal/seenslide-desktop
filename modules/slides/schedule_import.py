"""Parse a conference talk schedule from a CSV/text file.

Pure logic (no Qt) so the conference view can delegate here and the parser is
unit-testable headlessly. Tolerant by design — conference organizers hand
over whatever their spreadsheet exported:

  * comma / semicolon / tab separated (auto-detected), or plain lines with
    just a title;
  * optional header row ("title", "presenter"/"speaker"/"name" in any column
    order — column order is taken from it);
  * UTF-8 with or without BOM, latin-1 fallback;
  * blank lines and empty rows skipped; extra columns ignored;
  * a row with a speaker but no title becomes "Talk N".
"""
import csv
from pathlib import Path
from typing import List, Tuple

_TITLE_HEADERS = ("title", "talk", "talk title")
_PRESENTER_HEADERS = ("presenter", "speaker", "presenter name", "speaker name", "name")


def parse_talk_csv(path: str) -> List[Tuple[str, str]]:
    """Parse a schedule file into [(title, presenter), ...]."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = Path(path).read_text(encoding="latin-1")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return []

    # Delimiter: prefer the sniffer, fall back to whichever candidate
    # actually appears; a file with neither is title-only lines.
    sample = "\n".join(lines[:10])
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delim = next((d for d in (",", ";", "\t") if d in sample), ",")

    rows = [r for r in csv.reader(lines, delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        return []

    # Header detection + column order
    title_idx, presenter_idx = 0, 1
    first = [c.strip().lower() for c in rows[0]]
    is_header = any(c in _TITLE_HEADERS for c in first) or \
                any(c in _PRESENTER_HEADERS for c in first)
    if is_header:
        for i, c in enumerate(first):
            if c in _TITLE_HEADERS:
                title_idx = i
            elif c in _PRESENTER_HEADERS:
                presenter_idx = i
        rows = rows[1:]

    schedule: List[Tuple[str, str]] = []
    for r in rows:
        title = r[title_idx].strip() if len(r) > title_idx else ""
        presenter = r[presenter_idx].strip() if len(r) > presenter_idx else ""
        if not title and not presenter:
            continue
        schedule.append((title or f"Talk {len(schedule) + 1}", presenter))
    return schedule
