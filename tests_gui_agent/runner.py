"""Scenario runner: executes prewritten YAML steps against the real GUI.

Usage:
    venv/bin/python3 -m tests_gui_agent.runner tests_gui_agent/scenarios/smoke.yaml
    venv/bin/python3 -m tests_gui_agent.runner <scenario> --replay   # cached coords, no AI

Every step saves a screenshot into runs/<timestamp>/ — the film strip that
shows exactly what the screen looked like when something failed.
"""
import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from tests_gui_agent import actions
from tests_gui_agent.locator import Locator

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("runner")

HERE = Path(__file__).parent


class StepFailed(Exception):
    pass


class Runner:
    def __init__(self, scenario_path: str, mode: str = "locate"):
        self.scenario = yaml.safe_load(Path(scenario_path).read_text())
        self.locator = Locator(mode=mode)
        self.app = actions.App()
        self.run_dir = HERE / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir.mkdir(parents=True)
        self.step_no = 0
        self.report = []
        self._evidence = {}

    # -- helpers ----------------------------------------------------------

    def shot(self, tag: str = "") -> tuple:
        self.step_no += 1
        path = str(self.run_dir / f"step_{self.step_no:02d}_{tag}.png")
        size = actions.screenshot(path)
        return path, size

    def _record(self, step, ok, detail=""):
        entry = {"step": step, "ok": ok, "detail": detail}
        # Structured evidence stashed by the step handlers (screenshot used,
        # located bbox, click point) — consumed by the HTML film strip.
        entry.update(self._evidence)
        self._evidence = {}
        self.report.append(entry)
        status = "✓" if ok else "✗"
        logger.info(f"  {status} {json.dumps(step)[:110]} {detail}")

    # -- step implementations ---------------------------------------------

    def do_launch(self, spec):
        self.app.launch(wait=float(spec.get("wait", 8)),
                        cloud=bool(spec.get("cloud", False)))

    def do_kill(self, spec):
        self.app.kill()

    def do_wait(self, seconds):
        time.sleep(float(seconds))

    def do_click(self, spec):
        """Locate + click, with retries: a transient overlay (dialog,
        animation) or a one-off model miss shouldn't fail the scenario."""
        desc = spec["find"]
        retries = int(spec.get("retries", 2))
        r = {}
        for attempt in range(retries + 1):
            self.app.ensure_front()
            path, size = self.shot("before_click")
            r = self.locator.locate(desc, path, size)
            self._evidence = {"shot": path, "bbox": r.get("bbox"),
                              "click": r.get("center")}
            if r.get("found"):
                break
            if attempt < retries:
                logger.info(f"element not found (attempt {attempt + 1}) — retrying: {desc!r}")
                time.sleep(2.5)
        if not r.get("found"):
            raise StepFailed(f"element not found after {retries + 1} attempts: {desc!r}")
        cx, cy = r["center"]
        actions.click_shot_coords(cx, cy)
        return f"clicked ({cx},{cy}) bbox={r.get('bbox')}"

    def do_type(self, text):
        # $FIXTURES -> absolute path of tests_gui_agent/fixtures (lets
        # scenarios type file paths into dialogs machine-independently)
        text = str(text).replace("$FIXTURES", str(HERE / "fixtures"))
        actions.type_text(text)

    def do_key(self, key):
        actions.press_key(str(key))

    # -- PDF presenter ------------------------------------------------------

    def _deck_path(self, name: str) -> str:
        import os
        base = os.environ.get("SEENSLIDE_TEST_DECKS",
                              str(HERE.parent / "tests" / "pdfs"))
        p = Path(name)
        return str(p if p.is_absolute() else Path(base) / name)

    def do_virtual_mic(self, spec):
        """Create the virtual microphone and make it the system default —
        BEFORE the app opens its input stream, so recording is guaranteed to
        come from it regardless of stream-move policy."""
        from tests_gui_agent import audio
        if getattr(self, "_mic", None):
            return "virtual mic already up"
        self._mic = audio.VirtualMic()
        self._mic.create()
        return f"virtual mic is default source (node {self._mic.node_id})"

    def do_present_pdf(self, spec):
        """Start the fullscreen presenter on the primary monitor (async —
        use wait_presenter to block until the deck finishes). With
        narrate: true, a piper-tts narration timeline plays through a
        virtual microphone in sync with the page schedule."""
        import subprocess
        import mss as _mss
        idx = actions.primary_monitor()
        with _mss.mss() as sct:
            mon = sct.monitors[idx]
        geo = f"{mon['left']},{mon['top']},{mon['width']},{mon['height']}"
        pdf = self._deck_path(spec["file"])
        narration = None
        if spec.get("narrate"):
            from tests_gui_agent import audio
            narration = str(self.run_dir / "narration.wav")
            audio.build_narration(
                pdf, narration,
                pages=int(spec.get("max_pages", 0)),
                hold_first=float(spec.get("hold_first", 12)),
                interval=float(spec.get("page_interval", 5)))
            if not getattr(self, "_mic", None):
                self._mic = audio.VirtualMic()
                self._mic.create()
        cmd = [str(HERE.parent / "venv" / "bin" / "python3"),
               "-m", "tests_gui_agent.presenter",
               "--pdf", pdf, "--geometry", geo,
               "--interval", str(spec.get("page_interval", 5)),
               "--hold-first", str(spec.get("hold_first", 12)),
               "--max-pages", str(spec.get("max_pages", 0)),
               "--start-page", str(spec.get("start_page", 1))]
        self._presenter = subprocess.Popen(
            cmd, cwd=str(HERE.parent),
            stdout=open(self.run_dir / "presenter.log", "w"),
            stderr=subprocess.STDOUT)
        if narration:
            # timeline t=0 == presenter start; slots are silence-padded, so
            # the ~0.5s window-map skew is absorbed
            self._mic.play(narration)
        self._presented_pdf = pdf
        self._presented_pages = int(spec.get("max_pages", 0))
        time.sleep(2.0)  # let the window map and cover the screen
        if self._presenter.poll() is not None:
            raise StepFailed("presenter exited immediately — see presenter.log")
        return f"presenting {pdf}" + (" + narration" if narration else "")

    def do_wait_presenter(self, spec):
        if not getattr(self, "_presenter", None):
            raise StepFailed("no presenter running")
        timeout = float(spec.get("timeout", 300)) if isinstance(spec, dict) else 300
        try:
            self._presenter.wait(timeout=timeout)
        except Exception:
            self._presenter.kill()
            raise StepFailed("presenter did not finish in time")
        return "deck finished"

    # -- oracles -------------------------------------------------------------

    def do_verify_voice(self, spec):
        """The app recorded real audio from the (virtual) microphone:
        check the 'Voice recording stopped' log line, then the WAV itself —
        non-trivial peak proves synthetic speech actually flowed through."""
        import re as _re
        import shutil as _sh
        from tests_gui_agent.audio import wav_stats
        spec = spec or {}
        if not self.app.log_file.exists():
            raise StepFailed(f"sandbox log missing: {self.app.log_file}")
        stops = _re.findall(
            r"Voice recording stopped: ([\d.]+)s, (\d+) markers, (\S+)",
            self.app.log_file.read_text())
        if not stops:
            raise StepFailed("no 'Voice recording stopped' line in the app log")
        dur, markers, wav = float(stops[-1][0]), int(stops[-1][1]), stops[-1][2]
        min_dur = float(spec.get("min_duration", 5))
        min_markers = int(spec.get("min_markers", 1))
        min_peak = float(spec.get("min_peak", 0.05))
        if dur < min_dur:
            raise StepFailed(f"recording too short: {dur:.1f}s < {min_dur}s")
        if markers < min_markers:
            raise StepFailed(f"too few slide markers: {markers} < {min_markers}")
        wav_p = Path(wav)
        if not wav_p.exists():
            raise StepFailed(f"recorded WAV missing: {wav}")
        rec_dur, peak = wav_stats(str(wav_p))
        _sh.copy2(wav_p, self.run_dir / "recorded_voice.wav")
        if peak < min_peak:
            raise StepFailed(
                f"recorded audio is silence: peak {peak:.3f} < {min_peak} "
                f"(virtual mic not routed?)")
        return (f"app recorded {dur:.1f}s with {markers} slide markers, "
                f"WAV {rec_dur:.1f}s peak={peak:.3f}")

    def do_verify_db(self, spec):
        """Structural checks against the sandboxed SQLite database."""
        import sqlite3
        db = self.app.db_path
        if not db.exists():
            raise StepFailed(f"sandbox db missing: {db}")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        talks = conn.execute(
            "SELECT COUNT(*) c FROM talks").fetchone()["c"]
        # chronological across talks (talks play sequentially), 1..N inside
        # each talk — this order is what the PDF-match oracle's order check
        # relies on for multi-talk (conference) runs too
        slides = [dict(r) for r in conn.execute(
            "SELECT s.talk_id, s.sequence_number, s.image_path FROM slides s "
            "LEFT JOIN talks t ON t.talk_id = s.talk_id "
            "ORDER BY t.created_at, s.talk_id, s.sequence_number")]
        conn.close()

        if "talks" in spec and talks != spec["talks"]:
            raise StepFailed(f"expected {spec['talks']} talk(s), found {talks}")
        want = spec.get("slides", {})
        lo, hi = want.get("min", 0), want.get("max", 10**6)
        if not (lo <= len(slides) <= hi):
            raise StepFailed(
                f"expected {lo}..{hi} slides, found {len(slides)}: "
                f"{[s['sequence_number'] for s in slides]}")
        # numbering restarts at 1 inside every talk
        per_talk = {}
        for s in slides:
            per_talk.setdefault(s["talk_id"], []).append(s["sequence_number"])
        for tid, seqs in per_talk.items():
            if seqs != list(range(1, len(seqs) + 1)):
                raise StepFailed(
                    f"talk {tid}: sequence numbers not contiguous from 1: {seqs}")
        self._db_slides = slides
        return (f"{talks} talk(s), {len(slides)} slides, per-talk sequences "
                + " ".join(f"1..{len(v)}" for v in per_talk.values()))

    def do_show_cloud_code(self, spec):
        """Surface the cloud session code EARLY (right after the talk starts)
        so a human can open the public viewer while the talk is still live.
        Polls the sandbox DB for the first cloud talk id, which embeds the
        session code (XXX-NNNN-TALK-...)."""
        import sqlite3
        spec = spec or {}
        deadline = time.monotonic() + float(spec.get("timeout", 45))
        code = None
        while time.monotonic() < deadline and not code:
            if self.app.db_path.exists():
                try:
                    conn = sqlite3.connect(str(self.app.db_path))
                    row = conn.execute(
                        "SELECT talk_id FROM talks WHERE talk_id LIKE "
                        "'%-TALK-%' ORDER BY created_at DESC LIMIT 1").fetchone()
                    conn.close()
                    if row:
                        code = row[0].split("-TALK-")[0]
                except sqlite3.Error:
                    pass
            if not code:
                time.sleep(1.5)
        if not code:
            raise StepFailed("no cloud talk registered within the timeout")
        url = f"https://seenslide.com/{code}"
        (self.run_dir / "cloud_url.txt").write_text(url + "\n")
        logger.info(f"*** LIVE NOW: {url} ***")
        return url

    def do_verify_cloud(self, spec):
        """Web-side oracle: what the audience's viewer would see.

        Reads the cloud session code the sandboxed app registered (from its
        own DB), then queries the PUBLIC session endpoint — the same data the
        web viewer renders — and checks the slide count arrived."""
        import sqlite3
        import requests

        db = self.app.db_path
        if not db.exists():
            raise StepFailed(f"sandbox db missing: {db}")
        conn = sqlite3.connect(str(db))
        # Most robust source: cloud talk ids embed the session code
        # (XXX-NNNN-TALK-...). The sessions row's cloud_session_id proved
        # unreliable even when the cloud flow fully worked.
        code = None
        row = conn.execute(
            "SELECT talk_id FROM talks WHERE talk_id LIKE '%-TALK-%' "
            "ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            code = row[0].split("-TALK-")[0]
        else:
            row = conn.execute(
                "SELECT cloud_session_id FROM sessions "
                "WHERE cloud_session_id IS NOT NULL AND cloud_session_id != '' "
                "ORDER BY start_time DESC LIMIT 1").fetchone()
            if row:
                code = row[0]
        conn.close()
        if not code:
            raise StepFailed("no cloud session registered in the sandbox db")

        resp = requests.get(
            f"https://seenslide.com/api/cloud/session/{code}", timeout=15)
        if resp.status_code != 200:
            raise StepFailed(f"cloud session {code} not reachable "
                             f"(HTTP {resp.status_code})")
        data = resp.json()
        total = data.get("total_slides", 0)
        self._cloud_total = total   # verify_hidden cross-checks against this
        want = spec.get("slides", {})
        lo, hi = want.get("min", 1), want.get("max", 10**6)
        if not (lo <= total <= hi):
            raise StepFailed(
                f"cloud session {code} has {total} slides, expected {lo}..{hi}")
        self._cloud_code = code
        return (f"cloud session {code}: {total} slides visible to the web "
                f"viewer (https://seenslide.com/{code})")

    def do_verify_log(self, spec):
        """The sandbox app log must contain a line matching the pattern —
        proof that a specific internal action really ran (e.g. the unhide
        upload)."""
        import re as _re
        if not self.app.log_file.exists():
            raise StepFailed(f"sandbox log missing: {self.app.log_file}")
        hits = _re.findall(spec["pattern"], self.app.log_file.read_text())
        lo = int(spec.get("min", 1))
        if len(hits) < lo:
            raise StepFailed(
                f"log pattern {spec['pattern']!r}: {len(hits)} match(es), "
                f"need {lo}")
        return f"{len(hits)} log match(es) for {spec['pattern']!r}"

    def do_verify_hidden(self, spec):
        """Slide-gate oracle: the gate armed and flagged non-slide frames.
        Checks the armed log line, that >= min slides carry hidden metadata,
        and that hidden slides are LOCAL-ONLY (never uploaded — no cloud
        slide id in their metadata)."""
        import json as _json
        import sqlite3
        spec = spec or {}
        if spec.get("require_armed", True):
            log = self.app.log_file.read_text() if self.app.log_file.exists() else ""
            if "Slide gate armed from desktop base" not in log:
                raise StepFailed("slide gate never armed (no base-armed log line)")
        conn = sqlite3.connect(str(self.app.db_path))
        rows = conn.execute("SELECT sequence_number, metadata FROM slides").fetchall()
        hidden = []
        for seq, meta in rows:
            m = _json.loads(meta or "{}")
            if m.get("hidden"):
                hidden.append((seq, m))
        lo = int(spec.get("min", 1))
        hi = int(spec.get("max", 10**6))
        if not (lo <= len(hidden) <= hi):
            raise StepFailed(f"expected {lo}..{hi} hidden slides, found "
                             f"{len(hidden)} of {len(rows)}")
        # upload-leak check: cloud may hold at most the NON-hidden slides
        # (small slack for conference transition artifacts). Needs
        # verify_cloud to have run first (it records the cloud count).
        cloud_total = getattr(self, "_cloud_total", None)
        if cloud_total is not None:
            kept = len(rows) - len(hidden)
            slack = int(spec.get("cloud_slack", 2))
            if spec.get("cloud_exact"):
                # two-sided: an unhide that cleared the flag but failed to
                # upload leaves cloud < kept — that must fail too
                if cloud_total != kept:
                    raise StepFailed(
                        f"cloud count {cloud_total} != non-hidden local {kept}")
            elif cloud_total > kept + slack:
                raise StepFailed(
                    f"hidden slides leaked to the cloud: {cloud_total} online "
                    f"but only {kept} non-hidden locally (+{slack} slack)")
        return (f"{len(hidden)}/{len(rows)} slides hidden by the gate, "
                f"cloud={cloud_total} vs kept={len(rows) - len(hidden)}")

    def do_verify_talks(self, spec):
        """Conference oracle: the schedule became N talks, each talk's
        stored title/presenter matches the schedule row, slides are split
        between talks, and (the auto-advance guarantee) each talk's FIRST
        slide perceptually matches that talk's title page in the deck."""
        import sqlite3
        import fitz
        import imagehash
        from PIL import Image

        db = self.app.db_path
        if not db.exists():
            raise StepFailed(f"sandbox db missing: {db}")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        talks = [dict(r) for r in conn.execute(
            "SELECT talk_id, title, presenter_name FROM talks "
            "ORDER BY created_at")]
        want = int(spec["count"])
        if len(talks) != want:
            raise StepFailed(f"expected {want} talks, found {len(talks)}: "
                             f"{[t['title'] for t in talks]}")

        expected = spec.get("schedule") or []
        for i, exp in enumerate(expected):
            got = talks[i]["title"]
            if exp["title"].lower() not in got.lower():
                raise StepFailed(f"talk {i + 1} title mismatch: expected "
                                 f"{exp['title']!r}, db has {got!r}")

        min_slides = int(spec.get("min_slides", 1))
        title_pages = spec.get("title_pages") or []
        max_dist = int(spec.get("max_distance", 16))
        page_hashes = {}
        if title_pages:
            doc = fitz.open(self._deck_path(spec["file"]))
            for p in title_pages:
                pm = doc[p - 1].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                src = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
                page_hashes[p] = imagehash.dhash(src, hash_size=8)

        import json as _json
        detail = []
        for i, t in enumerate(talks):
            slides = [dict(r) for r in conn.execute(
                "SELECT sequence_number, image_path, metadata FROM slides "
                "WHERE talk_id = ? ORDER BY sequence_number", (t["talk_id"],))]
            if len(slides) < min_slides:
                raise StepFailed(f"talk {i + 1} ({t['title']!r}) has only "
                                 f"{len(slides)} slide(s), need {min_slides}")
            seqs = [s["sequence_number"] for s in slides]
            if seqs != list(range(1, len(seqs) + 1)):
                raise StepFailed(f"talk {i + 1} numbering not 1..{len(seqs)}: {seqs}")
            frag = f"talk{i + 1}:{len(slides)}sl"
            if i < len(title_pages):
                # first VISIBLE slide: manual Next-Talk transitions capture a
                # few app-screen frames first, which the gate hides — the
                # audience-facing deck must still open on the title page
                visible = [s for s in slides if not _json.loads(
                    s["metadata"] or "{}").get("hidden")]
                if not visible:
                    raise StepFailed(f"talk {i + 1} has no visible slides")
                first = visible[0]["image_path"]
                if not first or not Path(first).exists():
                    raise StepFailed(f"talk {i + 1} first visible slide image missing")
                cap = self._crop_letterbox(Image.open(first).convert("RGB"))
                d = imagehash.dhash(cap, hash_size=8) - page_hashes[title_pages[i]]
                if d > max_dist:
                    raise StepFailed(
                        f"talk {i + 1} first visible slide does not look like "
                        f"title page p{title_pages[i]} (dhash {d} > {max_dist})")
                frag += f" first=p{title_pages[i]}:{d}"
            detail.append(frag)
        return f"{len(talks)} talks — " + " ".join(detail)

    def do_verify_slides_match_pdf(self, spec):
        """Perceptual oracle: each stored slide must look like SOME presented
        page, and the matched pages must appear in presentation order.

        Best-match (not positional): dedup legitimately merges visually
        similar pages, so stored slide 3 may be PDF page 5 — comparing k↔k
        failed slides that were in fact perfect captures.
        """
        import shutil as _shutil
        import fitz
        import imagehash
        from PIL import Image

        slides = getattr(self, "_db_slides", None)
        if slides is None:
            raise StepFailed("run verify_db before verify_slides_match_pdf")
        pdf = self._deck_path(spec["file"])
        max_dist = int(spec.get("max_distance", 16))
        min_matched = int(spec.get("min_matched", len(slides)))
        max_pages = int(spec.get("max_pages", getattr(self, "_presented_pages", 0)))

        doc = fitz.open(pdf)
        n_pages = min(max_pages, doc.page_count) if max_pages else doc.page_count
        page_hashes = []
        for i in range(n_pages):
            pm = doc[i].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            src = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
            page_hashes.append(imagehash.dhash(src, hash_size=8))

        # keep the captured slide images with the run artifacts — the sandbox
        # is deleted at cleanup, and failures are undiagnosable without them
        slide_dir = self.run_dir / "slides"
        slide_dir.mkdir(exist_ok=True)

        matched, detail, matched_pages = 0, [], []
        for s in slides:
            k = s["sequence_number"]
            if not s["image_path"] or not Path(s["image_path"]).exists():
                detail.append(f"#{k}:missing")
                continue
            try:
                _shutil.copy2(s["image_path"], slide_dir / f"slide_{k:02d}.png")
            except Exception:
                pass
            cap = Image.open(s["image_path"]).convert("RGB")
            cap = self._crop_letterbox(cap)
            ch = imagehash.dhash(cap, hash_size=8)
            dists = [ch - ph for ph in page_hashes]
            best = min(range(len(dists)), key=lambda i: dists[i])
            detail.append(f"#{k}->p{best + 1}:{dists[best]}")
            if dists[best] <= max_dist:
                matched += 1
                matched_pages.append(best + 1)

        order_ok = matched_pages == sorted(matched_pages)
        if matched < min_matched or not order_ok:
            raise StepFailed(
                f"{matched}/{len(slides)} slides match a presented page "
                f"(need {min_matched}, order_ok={order_ok}); {' '.join(detail)} "
                f"— slide images saved to {slide_dir}")
        return (f"{matched}/{len(slides)} slides match presented pages in order "
                f"({' '.join(detail)})")

    @staticmethod
    def _crop_letterbox(im, thresh: int = 24):
        """Trim black letterbox bars so the hash compares slide content only."""
        from PIL import ImageOps
        g = im.convert("L")
        bbox = g.point(lambda p: 255 if p > thresh else 0).getbbox()
        return im.crop(bbox) if bbox else im

    def do_assert_screen(self, desc, retries: int = 2, delay: float = 2.0):
        last = None
        for attempt in range(retries + 1):
            self.app.ensure_front()
            path, size = self.shot("assert")
            self._evidence = {"shot": path}
            r = self.locator.judge(desc, path, size)
            if r.get("match"):
                return f"matched: {r.get('reason', '')}"
            last = r
            if attempt < retries:
                time.sleep(delay)
        raise StepFailed(f"screen assertion failed: {desc!r} — {last.get('reason', '')}")

    # -- main loop ----------------------------------------------------------

    def run(self) -> bool:
        name = self.scenario.get("name", "unnamed")
        steps = self.scenario.get("steps", [])
        logger.info(f"scenario: {name} ({len(steps)} steps) -> {self.run_dir}")
        ok = True
        try:
            for step in steps:
                (kind, spec), = step.items()
                try:
                    handler = getattr(self, f"do_{kind}")
                    detail = handler(spec) or ""
                    self._record(step, True, detail)
                except StepFailed as e:
                    self._record(step, False, str(e))
                    ok = False
                    break
                except Exception as e:
                    self._record(step, False, f"error: {e}")
                    ok = False
                    break
        finally:
            # never leave a fullscreen presenter covering the user's screen
            if getattr(self, "_presenter", None) and self._presenter.poll() is None:
                self._presenter.kill()
            # ...and never leave the user's default mic pointed at a dead node
            if getattr(self, "_mic", None):
                try:
                    self._mic.destroy()
                except Exception:
                    logger.exception("virtual mic teardown failed")
            # final state + app log land in the artifacts
            try:
                self.shot("final")
                if self.app.log_file.exists():
                    (self.run_dir / "seenslide.log").write_text(
                        self.app.log_file.read_text())
                # keep the sandbox DB too — the sandbox itself is deleted.
                # sqlite3 backup, not a file copy: the DB is in WAL mode, so
                # a plain copy of the .db file alone is empty/stale.
                if self.app.db_path.exists():
                    import sqlite3 as _sq
                    src = _sq.connect(str(self.app.db_path))
                    dst = _sq.connect(str(self.run_dir / "seenslide.db"))
                    with dst:
                        src.backup(dst)
                    src.close()
                    dst.close()
            except Exception:
                pass
            self.app.cleanup()
            (self.run_dir / "report.json").write_text(json.dumps({
                "scenario": name, "ok": ok, "ai_calls": self.locator.calls,
                "steps": self.report,
            }, indent=2))
        logger.info(f"{'PASS' if ok else 'FAIL'} — {self.locator.calls} AI calls, "
                    f"artifacts in {self.run_dir}")
        return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--replay", action="store_true",
                    help="cached coordinates only — zero AI calls")
    args = ap.parse_args()
    ok = Runner(args.scenario, mode="replay" if args.replay else "locate").run()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
