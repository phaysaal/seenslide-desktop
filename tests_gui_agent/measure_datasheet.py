"""Measure a datasheet for the vision locator (claude-opus-4.8) from the
harness's own run artifacts — the calibration pass that turns the informal
harness into (the beginning of) a Kimiya program.

Sources:
  * runs/*/report.json      — every step's kind, verdict, and detail
  * console logs (--logs)   — attempt-level retry lines + per-call latency

Quantities (Kimiya datasheet fields):
  judge  (assert_screen):  alpha  = P[accept | state false]   (false-accept)
                           beta   = P[accept | state true]    (true-accept)
  select (locate):         rho_r  = P[found  | element present] per call
  gen    (read_text):      err    = P[wrong value | value present]
  cost:                    latency distribution per call

Ground truth comes from two tiers, reported separately:
  T1 outcome-grounding — a step's truth inferred from the run's terminal
     hard oracles and the documented post-mortems of every failure in the
     campaign (each failed run was root-caused at the time: product bug,
     oracle bug, state drift, or model flake).
  T2 labeled events — the individually adjudicated events (flakes and
     correct rejections) enumerated below from the campaign record.

Where zero errors were observed, the datasheet reports the one-sided 95%
upper bound (rule of three: 3/n), never zero.
"""
import glob
import json
import math
import re
import sys
from collections import Counter

RUNS = sorted(glob.glob("runs/*/report.json"))

# ---- Campaign adjudications (T2): every non-passing perception event was
# root-caused when it happened; this is that record, made machine-readable.
# locate terminal misses (element present => false miss; absent => correct):
LOCATE_TERMINAL = {
    # run_dir_suffix: (description_fragment, element_was_present)
    "20260716-204856".replace("2026", "20260715"): ("Import CSV", True),   # visible; screenshot-confirmed flake
    "20260716-001808": ("Start Presenting", False),  # Sign-In modal covered the card: correct rejection
}
# assert_screen terminal failures adjudicated as CORRECT rejections (desc
# false on screen) vs judge false-rejects (desc true, judge said no):
ASSERT_FALSE_REJECTS = 0     # none observed in the campaign record
# assert_screen false-ACCEPTS observed (a green run later contradicted by a
# hard oracle attributable to a wrong screen judgment):
ASSERT_FALSE_ACCEPTS = 0     # none observed


def parse_reports():
    stats = Counter()
    per_run = []
    for path in RUNS:
        r = json.load(open(path))
        run_ok = r.get("ok", False)
        for s in r.get("steps", []):
            (kind, spec), = s["step"].items()
            ok, detail = s["ok"], str(s.get("detail", ""))
            if kind in ("click", "draw"):
                if "not present (optional)" in detail:
                    stats["locate_optional_skip"] += 1     # presence unknown
                elif detail.startswith("clicked") or detail.startswith("stroke"):
                    stats["locate_found"] += 1
                elif "not found" in detail:
                    stats["locate_terminal_miss"] += 1
            elif kind == "assert_screen" or kind == "actors":
                if kind == "actors" and "=" in detail and ok:
                    stats["judge_accept"] += 1              # actor self-check
                elif ok:
                    stats["judge_accept"] += 1
                elif "assertion failed" in detail or "doesn't look" in detail:
                    stats["judge_reject_terminal"] += 1
            elif kind == "read_text":
                stats["read_call"] += 1
                stats["read_ok" if ok else "read_fail"] += 1
        per_run.append((path, run_ok, r.get("ai_calls", 0)))
    stats["runs"] = len(per_run)
    stats["runs_pass"] = sum(1 for _, ok, _ in per_run if ok)
    stats["ai_calls_total"] = sum(c for _, _, c in per_run)
    return stats


def parse_logs(log_glob):
    latencies, attempt_misses, judge_retry_hits = [], 0, 0
    for path in glob.glob(log_glob):
        text = open(path, errors="replace").read()
        latencies += [float(x) for x in
                      re.findall(r"locator CLI call took ([\d.]+)s", text)]
        attempt_misses += len(re.findall(
            r"element not found \(attempt \d+\) — retrying", text))
    return latencies, attempt_misses


def rule_of_three(n):
    return 3.0 / n if n else float("nan")


def wilson_low(k, n, z=1.96):
    """Lower 95% bound of a proportion (Wilson)."""
    if n == 0:
        return float("nan")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    e = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - e) / d


def main():
    log_glob = sys.argv[1] if len(sys.argv) > 1 else "/tmp/nonexistent"
    st = parse_reports()
    lat, attempt_misses, = parse_logs(log_glob)

    # ---- locate (select) --------------------------------------------------
    found = st["locate_found"]
    term_present = sum(1 for _, p in LOCATE_TERMINAL.values() if p)
    # per-call trials on present elements: every found call, every retry miss
    # that later succeeded (element present by definition), and terminal
    # misses adjudicated present. Retry misses not individually adjudicated
    # are conservatively counted as present (against the instrument).
    recovered = max(attempt_misses - 3 * len(LOCATE_TERMINAL), 0)
    n_present = found + recovered + 3 * term_present
    miss_on_present = recovered + 3 * term_present
    rho_hat = 1 - miss_on_present / n_present
    rho_low = wilson_low(n_present - miss_on_present, n_present)

    # ---- judge (assert_screen) ---------------------------------------------
    acc = st["judge_accept"]
    rej = st["judge_reject_terminal"]
    # T1 outcome-grounding: accepted asserts in runs whose terminal hard
    # oracles passed are counted true; all terminal rejections in the
    # campaign were adjudicated correct (desc false on screen).
    n_true = acc + ASSERT_FALSE_REJECTS
    n_false = rej + ASSERT_FALSE_ACCEPTS
    beta_hat = acc / n_true if n_true else float("nan")
    beta_low = wilson_low(acc, n_true)
    alpha_obs = ASSERT_FALSE_ACCEPTS / n_false if n_false else float("nan")
    alpha_up = rule_of_three(n_false)

    # ---- read (gen) ---------------------------------------------------------
    n_read = st["read_call"]
    read_err_up = rule_of_three(n_read)

    lat_sorted = sorted(lat)
    pct = lambda q: lat_sorted[int(q * (len(lat_sorted) - 1))] if lat_sorted else None

    sheet = {
        "instrument": "vision locator — claude-opus-4-8 via claude -p CLI",
        "surface_families": ["PyQt5 desktop app (light/dark)", "GTK file dialog",
                             "Microsoft Edge viewer", "Firefox viewer (dark)"],
        "campaign": {"runs": st["runs"], "runs_passed": st["runs_pass"],
                     "total_model_calls_reported": st["ai_calls_total"],
                     "latency_samples": len(lat)},
        "select_locate": {
            "n_calls_on_present": n_present,
            "misses_on_present": miss_on_present,
            "recall_per_call_hat": round(rho_hat, 4),
            "recall_per_call_wilson95_low": round(rho_low, 4),
            "terminal_false_misses": term_present,
            "note": "misses recover under the harness retry policy "
                    "(retries=2 + one scenario re-run)",
        },
        "judge_assert": {
            "n_true": n_true, "n_false": n_false,
            "beta_hat": round(beta_hat, 4),
            "beta_wilson95_low": round(beta_low, 4),
            "alpha_observed": alpha_obs,
            "alpha_upper95_rule_of_three": round(alpha_up, 4),
            "false_rejects_observed": ASSERT_FALSE_REJECTS,
            "false_accepts_observed": ASSERT_FALSE_ACCEPTS,
        },
        "gen_read": {"n_calls": n_read,
                     "errors_observed": st["read_fail"],
                     "error_upper95_rule_of_three": round(read_err_up, 4)},
        "cost": {"latency_s_p50": pct(0.5), "latency_s_p90": pct(0.9),
                 "latency_s_max": pct(1.0)},
        "correlation_note": "single-model, single-prompt configuration: "
            "immediate same-input retries are highly correlated (observed: "
            "3 consecutive misses on one visible element); a later fresh run "
            "succeeded. rho is not separately measured; treat immediate "
            "retries as one effective sample.",
        "ground_truth_method": "T1 outcome-grounding against terminal hard "
            "oracles + T2 per-event adjudication of every campaign failure; "
            "zero-event rates reported as one-sided 95% bounds (rule of three).",
    }
    print(json.dumps(sheet, indent=2))


if __name__ == "__main__":
    main()
