"""Anonymous-to-claimed nudge state machine.

Three tiers, escalating in pressure:

  tier_a (gentle):    after the first slide is captured on this device.
                      Shown once, dismissable.
  tier_b (reminder):  re-shown after `TIER_B_INTERVAL_SECONDS` if the user
                      is still anonymous. Repeats indefinitely until claimed
                      or the enforce tier kicks in.
  tier_c (enforce):   when `slides_since_last_dismiss` reaches
                      `TIER_C_SLIDE_THRESHOLD`, a blocking dialog is shown
                      that the user cannot dismiss without registering.

State is persisted at ~/.config/seenslide/.nudge_state.json. The state is
keyed to the device — when a user signs in (claims/logs in), call
`reset()` to clear the counter and prompt history so their next anonymous
session on the same device starts fresh.

Counter semantics:
  total_slides              — cumulative count of slides captured on this
                              device while anonymous (kept for stats /
                              analytics; not used for tier decisions).
  slides_since_last_dismiss — slides captured since the last time the
                              user dismissed *any* nudge dialog. Reset
                              to 0 in mark_shown(). The enforce tier
                              uses this so that slides captured WHILE a
                              dialog was on screen don't push the user
                              instantly from a "Maybe later" dismiss into
                              the blocking ENFORCE tier.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 2 days. Spec said "2/3 days" — 2 picked deliberately as the lower bound
# so users see the reminder sooner rather than later.
TIER_B_INTERVAL_SECONDS = 2 * 24 * 3600
TIER_C_SLIDE_THRESHOLD = 50

STATE_FILE = Path.home() / ".config" / "seenslide" / ".nudge_state.json"


class NudgeTier(str, Enum):
    GENTLE = "gentle"      # tier (a)
    REMINDER = "reminder"  # tier (b)
    ENFORCE = "enforce"    # tier (c)


@dataclass
class NudgeState:
    total_slides: int = 0
    slides_since_last_dismiss: int = 0
    tier_a_shown_at: float = 0.0
    tier_b_last_shown_at: float = 0.0
    tier_c_shown: bool = False

    # ── Persistence ─────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "NudgeState":
        try:
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text())
                # `slides_since_last_dismiss` defaults to 0 for pre-existing
                # state files. Worst case for an upgrading user: they get
                # the next TIER_C_SLIDE_THRESHOLD slides as a fresh budget
                # before enforce fires — equivalent to a clean install.
                return cls(
                    total_slides=int(data.get("total_slides", 0)),
                    slides_since_last_dismiss=int(
                        data.get("slides_since_last_dismiss", 0)
                    ),
                    tier_a_shown_at=float(data.get("tier_a_shown_at", 0.0)),
                    tier_b_last_shown_at=float(data.get("tier_b_last_shown_at", 0.0)),
                    tier_c_shown=bool(data.get("tier_c_shown", False)),
                )
        except Exception as e:
            logger.warning(f"nudge state unreadable, starting fresh: {e}")
        return cls()

    def save(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(asdict(self), indent=2))
            STATE_FILE.chmod(0o600)
        except Exception as e:
            logger.warning(f"could not save nudge state: {e}")

    # ── Mutators ────────────────────────────────────────────────────

    def record_slide(self) -> None:
        self.total_slides += 1
        self.slides_since_last_dismiss += 1
        self.save()

    def mark_shown(self, tier: NudgeTier) -> None:
        now = time.time()
        if tier == NudgeTier.GENTLE:
            self.tier_a_shown_at = now
        elif tier == NudgeTier.REMINDER:
            self.tier_b_last_shown_at = now
        elif tier == NudgeTier.ENFORCE:
            self.tier_c_shown = True
        # User has just been prompted; reset the budget so escalation
        # requires fresh activity before the next tier can fire.
        self.slides_since_last_dismiss = 0
        self.save()

    def reset(self) -> None:
        """Called after a successful claim/login — start over from zero."""
        self.total_slides = 0
        self.slides_since_last_dismiss = 0
        self.tier_a_shown_at = 0.0
        self.tier_b_last_shown_at = 0.0
        self.tier_c_shown = False
        self.save()

    # ── Evaluators ──────────────────────────────────────────────────

    def evaluate(self, is_anonymous: bool) -> Optional[NudgeTier]:
        """Decide which tier (if any) should be shown right now.

        Caller is responsible for actually displaying it and then calling
        `mark_shown(tier)`. Returns the highest-priority tier ready to fire.
        """
        if not is_anonymous:
            return None

        # Enforce tier: TIER_C_SLIDE_THRESHOLD slides since the last
        # dismissed dialog, and not yet shown. Using `since_last_dismiss`
        # (not total_slides) prevents slides captured while a gentle or
        # reminder dialog was open from racing the user straight into the
        # blocking enforce dialog the instant they dismiss.
        if (
            self.slides_since_last_dismiss >= TIER_C_SLIDE_THRESHOLD
            and not self.tier_c_shown
        ):
            return NudgeTier.ENFORCE

        # Gentle tier: first slide captured, never shown
        if self.total_slides >= 1 and self.tier_a_shown_at == 0.0:
            return NudgeTier.GENTLE

        # Reminder tier: gentle has been shown, interval elapsed
        if (
            self.tier_a_shown_at > 0
            and self.total_slides > 0
            and (time.time() - max(self.tier_a_shown_at, self.tier_b_last_shown_at))
                >= TIER_B_INTERVAL_SECONDS
        ):
            return NudgeTier.REMINDER

        return None
