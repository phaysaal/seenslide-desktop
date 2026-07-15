"""Vision locator: turn "the button labeled X" into screen coordinates.

The only AI-powered layer of the GUI harness. Everything else is
deterministic; this answers exactly two questions about a screenshot:

  locate(description)  -> bounding box of a UI element
  judge(description)   -> does the screen match this description?

Backends (auto-selected):
  * anthropic SDK      — when ANTHROPIC_API_KEY is set
  * `claude -p` CLI    — headless Claude Code on the user's subscription

Answers are cached in .cache/coords.json keyed by (description, screen
size), so `--replay` runs make zero AI calls.
"""
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
CACHE_FILE = HERE / ".cache" / "coords.json"

LOCATE_PROMPT = """Look at the screenshot image at {path} (a {w}x{h} pixel screen capture).

Find this UI element: {desc}

Respond with ONLY a JSON object, no other text:
{{"found": true, "bbox": [x0, y0, x1, y1]}}
where bbox is the element's bounding box in pixels of the original {w}x{h} image
(x0,y0 = top-left corner, x1,y1 = bottom-right corner).
If the element is not visible, respond {{"found": false}}."""

JUDGE_PROMPT = """Look at the screenshot image at {path} (a {w}x{h} pixel screen capture).

Question: does the screen show the following? {desc}

Respond with ONLY a JSON object, no other text:
{{"match": true or false, "reason": "one short sentence"}}"""

READ_PROMPT = """Look at the screenshot image at {path} (a {w}x{h} pixel screen capture).

Read the following value off the screen, exactly as displayed: {desc}

Respond with ONLY a JSON object, no other text:
{{"found": true or false, "text": "the exact value"}}"""


class Locator:
    #: UI-element localization doesn't need the top-tier model — Opus 4.8
    #: boxes labeled buttons on a clean UI just as well. Override with
    #: SEENSLIDE_LOCATOR_MODEL if needed.
    DEFAULT_MODEL = "claude-opus-4-8"

    def __init__(self, mode: str = "locate", model: str = None):
        """mode: 'locate' (fresh AI calls, refresh cache) or 'replay'
        (cache only — zero AI calls, fails on cache miss)."""
        self.mode = mode
        self.model = model or os.environ.get("SEENSLIDE_LOCATOR_MODEL", self.DEFAULT_MODEL)
        self._cache = {}
        if CACHE_FILE.exists():
            try:
                self._cache = json.loads(CACHE_FILE.read_text())
            except Exception:
                self._cache = {}
        self.calls = 0

    # -- public ---------------------------------------------------------

    def locate(self, desc: str, shot_path: str, size) -> dict:
        """-> {"found": bool, "bbox": [x0,y0,x1,y1], "center": [cx,cy]}"""
        key = f"locate|{size[0]}x{size[1]}|{desc}"
        if self.mode == "replay":
            if key in self._cache:
                return self._cache[key]
            raise LookupError(
                f"replay mode: no cached coords for {desc!r} — run with --locate first"
            )
        result = self._ask(LOCATE_PROMPT.format(
            path=shot_path, w=size[0], h=size[1], desc=desc))
        if result.get("found") and "bbox" in result:
            x0, y0, x1, y1 = result["bbox"]
            result["center"] = [int((x0 + x1) / 2), int((y0 + y1) / 2)]
            self._cache[key] = result
            self._save_cache()
        return result

    def read(self, desc: str, shot_path: str, size) -> dict:
        """-> {"found": bool, "text": str} — never cached (values change)."""
        self.calls += 1
        return self._ask(READ_PROMPT.format(
            path=shot_path, w=size[0], h=size[1], desc=desc))

    def judge(self, desc: str, shot_path: str, size) -> dict:
        """-> {"match": bool, "reason": str}. Never cached (state changes)."""
        return self._ask(JUDGE_PROMPT.format(
            path=shot_path, w=size[0], h=size[1], desc=desc))

    # -- backends -------------------------------------------------------

    def _ask(self, prompt: str) -> dict:
        self.calls += 1
        if os.environ.get("ANTHROPIC_API_KEY"):
            raw = self._ask_sdk(prompt)
        else:
            raw = self._ask_cli(prompt)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.error(f"locator: no JSON in response: {raw[:300]}")
            return {"found": False, "match": False, "reason": "no JSON in model reply"}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.error(f"locator: bad JSON: {m.group(0)[:300]}")
            return {"found": False, "match": False, "reason": "bad JSON"}

    def _ask_sdk(self, prompt: str) -> str:
        import anthropic
        # The prompt references a file path; the SDK needs the image inline.
        path = re.search(r"image at (\S+) ", prompt).group(1)
        img_b64 = base64.standard_b64encode(Path(path).read_bytes()).decode()
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=self.model or "claude-opus-4-8",
            max_tokens=300,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/png",
                                             "data": img_b64}},
                {"type": "text", "text": prompt},
            ]}],
        )
        return resp.content[0].text

    def _ask_cli(self, prompt: str) -> str:
        """Headless Claude Code: it Reads the screenshot itself."""
        claude = shutil.which("claude")
        if not claude:
            raise RuntimeError("neither ANTHROPIC_API_KEY nor `claude` CLI available")
        cmd = [claude, "-p", prompt, "--allowedTools", "Read",
               "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        t0 = time.time()
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            cwd="/tmp",  # neutral cwd: don't load this repo's project context
        )
        logger.info(f"locator CLI call took {time.time()-t0:.1f}s")
        if out.returncode != 0:
            logger.error(f"claude CLI failed: {out.stderr[:300]}")
        return out.stdout or ""

    def _save_cache(self):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(self._cache, indent=2))
