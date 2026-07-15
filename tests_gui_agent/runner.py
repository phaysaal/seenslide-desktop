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
        self.app.launch(wait=float(spec.get("wait", 8)))

    def do_kill(self, spec):
        self.app.kill()

    def do_wait(self, seconds):
        time.sleep(float(seconds))

    def do_click(self, spec):
        desc = spec["find"]
        self.app.ensure_front()
        path, size = self.shot("before_click")
        r = self.locator.locate(desc, path, size)
        self._evidence = {"shot": path, "bbox": r.get("bbox"),
                          "click": r.get("center")}
        if not r.get("found"):
            raise StepFailed(f"element not found: {desc!r}")
        cx, cy = r["center"]
        actions.click_shot_coords(cx, cy)
        return f"clicked ({cx},{cy}) bbox={r.get('bbox')}"

    def do_type(self, text):
        actions.type_text(str(text))

    def do_key(self, key):
        actions.press_key(str(key))

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
            # final state + app log land in the artifacts
            try:
                self.shot("final")
                if self.app.log_file.exists():
                    (self.run_dir / "seenslide.log").write_text(
                        self.app.log_file.read_text())
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
