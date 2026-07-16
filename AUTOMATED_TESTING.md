# SeenSlide Automated Testing — Methodology & Results

Documentation of the complete automated-testing effort across the SeenSlide
desktop app (this repo), the cloud backend (`../SeenSlide`, Railway/FastAPI/
PostgreSQL at seenslide.com), and the web viewer (Svelte). Written July
2026, covering releases v1.0.35–v1.0.40.

Two purposes:

1. **Repeatability** — everything here can be re-run with the commands
   given; the design decisions and pitfalls are recorded so future test
   work doesn't rediscover them.
2. **Demonstration** — this project built what we believe is a novel
   **LLM-driven GUI test harness**: prewritten deterministic steps whose
   *perception* (finding buttons, judging screens, reading values off
   pixels) is delegated to a vision LLM, combined with hard non-visual
   oracles (SQLite, public HTTP APIs, perceptual image hashing, audio
   waveform analysis). Part II documents that system and its measured
   effectiveness: **10 real production bugs found**, all fixed and shipped.

---

# Part I — Non-GUI automated tests

## I.1 Methodology

Three layers, ordered by distance from the code:

| Layer | Tool | Runs against | Gate |
|---|---|---|---|
| Unit / integration | pytest (`tests/`, 65 tests) | in-process, temp dirs, mocks | CI on every push/PR **and** required by all three release builds (`.github/workflows/tests.yml`, `build-release.yml needs: test`) |
| HTTP security | `tests_gui_agent/w6_auth_security.py` | **production** seenslide.com | manual, throwaway accounts, self-purging |
| DB atomicity | `../SeenSlide/testing_scripts/test_credit_transactions.py` | **production** PostgreSQL | manual, throwaway rows, self-purging |

Principles:

- **Test the real thing when the risk is integration.** Auth-token
  semantics and transaction atomicity are properties of the deployed
  system (FastAPI + asyncpg + Postgres together), so those tests run
  against production with disposable data rather than against mocks that
  would encode the same wrong assumptions as the code.
- **Throwaway data must be self-evidently throwaway.** Test accounts use
  `@harness.invalid` (RFC 2606 reserved TLD — can never receive mail or
  collide with a person); test DB rows use `tx-test-<uuid>` ids. Purges
  are **name-gated inside the SQL itself** (`WHERE email LIKE
  '%@harness.invalid'`-style), never lists of ids collected elsewhere.
- **Regression tests are written at fix time.** Every bug fixed during
  this effort that is unit-testable got a pytest module the same day
  (`test_voice_markers.py`, `test_session_persistence.py`,
  `test_tmp_storage_migration.py`).

## I.2 Test-case inventory (pytest, `tests/`)

| File | What it verifies | How |
|---|---|---|
| `test_dedup_engine.py` | Per-talk dedup scoping: `reset()` clears history and restarts numbering; `inject_capture()` publishes SLIDE_UNIQUE and seeds history (conference title-slide carry-over) | Real `DeduplicationEngine` with synthetic PIL images |
| `test_perceptual_strategy.py` | dhash + **tiled pixel-diff** (144px thumbnail, 8×8 grid, tolerance 4.0) catches a single changed line on an otherwise identical slide; near-identical frames still dedup | Rendered text images differing by one line |
| `test_blank_frame.py` | Blank-frame guard drops featureless frames (blackout key, unmapped surface) but never a letterboxed slide | Grayscale std-dev threshold on synthetic frames |
| `test_outbox_drain.py` | Upload outbox: failed uploads enqueue; drain retries oldest-first; 404 drops the row; success removes it; attempt/age caps enforced | Mocked cloud provider, real SQLite outbox table |
| `test_sqlite_provider.py` | WAL mode, `busy_timeout`, serialized `_write()` with rollback (multi-statement deletes atomic), 6-thread concurrency, `quick_check` corruption detection, backup/restore (garbage DB → last-known-good restored) | Real SQLite files in tmp dirs, deliberate corruption |
| `test_title_matcher.py` | Conference OCR matching: token-fuzzy title coverage ≥ 0.75 + presenter found (0.90 title-only); multi-line titles; presenter inside a multi-author list; agenda slides do NOT match | Real OCR (RapidOCR) on rendered fixture slides |
| `test_schedule_import.py` | CSV/TSV/semicolon talk-schedule parsing, blank/malformed lines | Pure function, text fixtures |
| `test_config_defaults.py` | **Drift guard**: `ConfigLoader.load_defaults()` must match `config/config.yaml` (a silent divergence once sent all data to `/tmp`) | Field-by-field comparison |
| `test_api_url.py` | `core/identity.py` rejects non-https `api_url` (localhost exempt for dev/relay) | Direct calls |
| `test_voice_markers.py` | **Regression (bug #2)**: local-only voice recordings get SLIDE_UNIQUE markers; the cloud flush queue stays empty without an uploader | Orchestrator with mocked recorder + real event bus |
| `test_session_persistence.py` | **Regression (bug #6)**: `orchestrator.update_session()` persists the session row (cloud_session_id!) to SQLite; a failed persist doesn't abort talk start | Mocked storage manager |
| `test_tmp_storage_migration.py` | **Regression (bug #1)**: one-time `/tmp/seenslide` rescue migrates to the default path, rewrites stored image-path prefixes in the DB, **never** fires for custom base paths (test sandboxes), never overwrites an existing target DB | Isolated fake HOME + fake legacy dir |

Run: `venv/bin/python3 -m pytest tests/ -q` → 65 passed.

## I.3 HTTP-level auth security (`tests_gui_agent/w6_auth_security.py`)

The web viewer authenticates by **magic link** (email is only an
identifier; no verification mail matters; the token *is* the credential).
The security properties live at the HTTP layer, so they are tested there.
The freshly-created token is read from the `magic_links` table — exactly
what an inbox would have received — to complete login without any mailbox.

Checks (all against production, two `@harness.invalid` accounts,
auto-purged): login issues a working session; **the token is single-use**
(replay rejected); the two accounts are distinct `user_id`s; **logout
invalidates the session** (protected endpoint 401 afterwards).

Note: the "wrong-PIN lockout" (`MAX_FAILED_ATTEMPTS=10`, 15-min lock) is a
desktop/phone identity feature — the web path has no PIN, so it is not a
web test.

Run: `SS_DBURL=<railway DATABASE_PUBLIC_URL> venv/bin/python3
tests_gui_agent/w6_auth_security.py` (add `--keep` to skip the purge,
`--purge` to purge only).

## I.4 DB-level credit atomicity (`../SeenSlide/testing_scripts/test_credit_transactions.py`)

Exercises the real `CreditManager` through
`DatabaseManager.transaction()` against the production database with a
throwaway `viewer_users` row: grant (+50, one logged transaction), deduct
(−20, second transaction), insufficient-funds refusal (balance untouched),
and the decisive **rollback test** — inside a transaction the uncommitted
balance is visible (+500), a forced error rolls it back exactly to the
pre-transaction value.

Run (SeenSlide repo, its venv has asyncpg — NOT psycopg2):
`SS_DBURL=<url> venv/bin/python3 testing_scripts/test_credit_transactions.py`

## I.5 Non-GUI results

All 65 pytest cases green and gating releases. The two production-level
suites pass fully. Bugs found *by these tests* are counted in the unified
table in Part III (the HTTP/DB suites found #8, #9, #10; the pytest
modules are regression locks for #1, #2, #6).

---

# Part II — LLM-driven GUI testing

## II.1 The idea

Conventional GUI automation binds tests to selectors/accessibility ids —
brittle, and impossible for surfaces you don't control (native file
dialogs, browser chrome, two different browsers). This harness splits the
problem:

- **Control flow is deterministic**: scenarios are prewritten YAML step
  lists. No agent improvisation; a run either follows the script or fails.
- **Perception is an LLM**: a vision model receives a screenshot and a
  natural-language description ("the red 'End Presentation' button") and
  returns coordinates (`locate`), a boolean judgment (`judge`: "does the
  screen show X?"), or a value read off the pixels (`read`: "the
  8-character join code in the dialog").
- **Truth is never only visual**: every scenario ends in *hard oracles* —
  SQLite queries, public HTTP endpoints, perceptual image hashing against
  the source PDF, audio waveform peak analysis — so a plausible-looking
  screen can't fake a pass.

## II.2 Architecture (`tests_gui_agent/`)

```
scenario.yaml ──▶ runner.py ──▶ locator.py ──▶ claude -p (opus-4.8, vision)
                     │               └─ coords cache (.cache/coords.json, --replay = 0 AI calls)
                     ├─▶ actions.py     xdotool click/type/key/drag · mss screenshots
                     │                  browser ACTORS (window-cropped shots, offset clicks)
                     │                  sandboxed App lifecycle
                     ├─▶ presenter.py   fitz PDF → fullscreen Qt window (the "human presenting")
                     ├─▶ audio.py       piper-TTS + pw-loopback virtual microphone
                     ├─▶ relay.py       local HTTP relay → cloud (kill = network outage)
                     └─▶ report_html.py film-strip HTML report (bbox + click crosshair per step)
```

**Locator** (`locator.py`). Model: `claude-opus-4-8` (localizing labeled
buttons on clean UIs doesn't need the top tier; ~2× faster). Backend: the
`claude -p` CLI headlessly (no API key needed) or the Anthropic SDK if
`ANTHROPIC_API_KEY` is set. Calls take ~5–15 s. Coordinates are cached by
`(mode, screen size, description)`; `--replay` runs entire scenarios with
zero AI calls. `read` results are never cached (values change per run).

**Input** (`actions.py`). xdotool synthesizes OS-level events —
indistinguishable from a human, so the app's input-monitor capture
trigger fires naturally. Multi-monitor: the primary is resolved via
xrandr and clicks are offset-corrected; verified on 1- and 2-monitor
setups.

**Sandboxing.** The desktop app under test runs with: a fresh temp
`$HOME` (settings/collections/DB isolated), `PYTHON_KEYRING_BACKEND=null`
(the real Secret Service once popped the user's password-manager unlock
dialog mid-run), a **random pre-seeded device id** for cloud runs — the
machine-id fallback would silently resurrect the developer's real
anonymous account and pollute it — and `SEENSLIDE_TEST_ON_TOP=1` (an
in-app hook; Mutter ignores external raise requests). The sandbox config
is the real project config with `storage.base_path` redirected (a minimal
config once hid bug #1 by accident).

**The presenter** (`presenter.py`). Renders PDF pages fullscreen on a
chosen monitor with a schedule (`--hold-first`, `--interval`,
`--start-page/--max-pages` for Next-Talk segments). Must bind the Qt
window to the target `QScreen` and use `showFullScreen()` — Mutter
mis-places frameless `setGeometry` windows on multi-monitor.

**Synthetic voice** (`audio.py`). piper-TTS (`en_US-lessac-medium`)
speaks one line per PDF page, silence-padded to the exact presentation
schedule. A **pw-loopback** pair (sink `ss-mic-in` → device-class source
"SS-Test-Mic") becomes the system default microphone for the run and is
always restored. This was the only working recipe on PipeWire:
`pw-cli create-node` silently creates nothing, and wireplumber refuses
stream-class nodes as default. Audio *output* is verified by recording
the default sink's monitor (`pw-record --properties
'{ stream.capture.sink=true }'`) and asserting waveform peaks — including
a `max_peak` mode to prove *silence* (paused playback).

**Network fault injection** (`relay.py`). The sandbox app reaches the
cloud through `http://127.0.0.1:8899` → relay → seenslide.com. Killing
the relay is a clean outage (instant connection-refused); restarting it
restores service. No host network changes. Pitfall: the relay must strip
`Content-Encoding` (requests pre-decodes upstream bodies).

**Two-browser actors** (web testing). `actors: {A: edge, B: firefox}`
binds names to real browser windows by title + browser marker (largest
match wins, self-verified by an AI judge at registration). Targeted steps
(`target: A|B`) crop the screenshot to that window's rect (clamped to the
virtual screen — Mutter parks windows a few px offscreen) and offset
clicks to the window origin — two viewers of the same page can't be
confused, and nothing outside the window is ever clicked (the developer's
terminal shared a monitor with actor B throughout).

**Step DSL** (complete): `launch` (sandbox app, `cloud:`, `api_url:`),
`kill`, `wait`, `click` (with `retries`, `optional:` for maybe-absent
elements like permission prompts), `type` (with `$FIXTURES` and `$VAR`
expansion), `key`, `assert_screen` (AI judge, retries, `$VAR` expansion),
`read_text` (AI reads a value into `$VAR`), `draw` (drag stroke — ink
annotations and AI region selection), `actors`, `present_pdf`
(`narrate:`, `start_page:`), `wait_presenter`, `virtual_mic`,
`play_audio` (TTS through the mic), `relay`, `show_cloud_code` (surfaces
the live viewer URL mid-run, exports `$CLOUD_URL`).

**Oracles**: `verify_db` (slide counts, per-talk 1..N contiguity),
`verify_slides_match_pdf` (each stored slide dhash-matched **best-match**
against source pages + presentation-order check; positional k↔k matching
fails legitimately when dedup merges similar pages), `verify_cloud`
(public session endpoint — what the audience actually sees; slide + viewer
bounds), `verify_talks` (conference split: count, titles vs schedule,
first *visible* slide of each talk perceptually equals its title page),
`verify_voice` (app log line + recorded WAV duration/peak),
`verify_hidden` (slide gate armed; hidden counts; `cloud == kept` exactly
— an upload leak or a failed unhide both fail), `verify_outbox` (pending
row count), `verify_audio_out` (sink-monitor recording peak / silence),
`verify_log` (regex proof an internal action ran).

**Artifacts.** Every run directory keeps: numbered screenshots per step,
the film-strip HTML report (red bbox + yellow click crosshair), the
sandbox app log, the sandbox DB (saved via **sqlite3 backup API** — a
plain file copy of a WAL-mode DB is empty), presenter/relay logs,
narration + recorded WAVs, `report.json`.

## II.3 Methodology rules learned the hard way

- **State-tolerant steps.** Runs fail mid-way; the next run inherits the
  leftovers. Steps that open/join/play must be `optional:` or
  leave-then-redo (voice chat rejoins because a call surviving from a
  previous run holds a **dead mic node** and transmits silence).
- **Don't interact during continuous playback.** The locator's think-time
  (5–15 s) is real time: a marker-walk test during playback drifted past
  markers nondeterministically. Pause first, then walk.
- **Distinguish product bugs from oracle bugs.** Several "failures" were
  wrong assertions (a deck whose page 4 *is* a title slide; a voice bar
  that has no speaking indicator; `/api/credits/balance` as an auth probe).
  The discipline: on failure, read the artifacts before touching product
  code.
- **Locator flakiness exists.** The vision model occasionally refuses to
  find a plainly visible element 3× in a row; a plain re-run passed.
  Policy: re-run once before treating a locate-miss as a regression.
- **Cleanup discipline.** Purge only data whose harness origin is provable
  *in the delete statement itself* (name patterns like `'W2 Replay'`,
  `@harness.invalid`) — never ids collected from logs. This rule exists
  because a session collected from a server log line (`POU-7304`) was
  wrongly deleted and had to be reconstructed from surviving volume files
  (it was recoverable; the lesson stands). Also: the server caches
  sessions in memory — DB-level deletes keep serving until a redeploy.
- **The desktop presenter covers a monitor.** Web actor A (same monitor)
  joins live talks *early* and is verified after the deck ends; the
  unobstructed actor B does the mid-talk checks, including the late-join.
- **Autoplay policies are features.** Live audio and replay need a user
  gesture ("Listen Live" / play button); scenarios click them rather than
  reporting silence as a bug.

## II.4 Desktop scenarios (P0–P5)

| Scenario | What it proves | Key oracles |
|---|---|---|
| `smoke.yaml` (P0) | App launches sandboxed; all main views reachable by AI-located navigation; verified on 1- and 2-monitor setups | assert_screen chain |
| `direct_talk.yaml` (P1) | Full talk: form → countdown → real PDF presented fullscreen → screen captured → dedup → local store → End | verify_db, verify_slides_match_pdf (8/8 pages in order, dhash 0–6) |
| `direct_talk_cloud.yaml` (P1) | Same plus: collection created via real UI under a **throwaway anonymous identity**, slides visible on the public web endpoint | + verify_cloud |
| `direct_talk_voice.yaml` (P2) | Synthetic narration through the virtual mic; the app records it with slide markers | verify_voice (85.9 s, 13 markers, peak 1.0) |
| `direct_talk_voice_cloud.yaml` (P2-live) | A complete "real talk" watchable live from the web (slides + 1 s audio chunks); `show_cloud_code` logs the URL mid-run for a human to watch | + verify_cloud; live-viewed at seenslide.com/LRJ-9902 |
| `conference.yaml` (P3) | CSV schedule import through the **native GTK file dialog** (Ctrl+L location bar), OCR **auto-advance** splitting a synthetic 3-talk deck with zero manual clicks; slide gate hides post-deck app frames; cloud == kept exactly | verify_talks (each talk's first slide == its title page, dhash 0), verify_hidden (cloud_slack 0), verify_cloud, verify_voice |
| `conference_manual.yaml` (P4b) | Manual "Next Talk" advance between presenter segments (`--start-page`); talks split at the clicks; between-talk app frames gated | verify_talks (first *visible* slide == title page) |
| `unhide.yaml` (P4a) | The gate's recovery path: blurred hidden slide in Sessions view → "Is it a slide? Unhide" badge → flag cleared **and** after-the-fact cloud upload | verify_log (upload line), verify_hidden `cloud_exact` (two-sided: a failed upload also fails) |
| `offline_outbox.yaml` (P5) | Network dies mid-talk: pages queue in `upload_outbox`; on recovery the 30 s worker backfills; final deck complete online | verify_outbox (rows then 0), verify_log, verify_cloud == kept |

Supporting fixture: `make_conference_deck.py` generates the 3-talk deck
(multi-line titles, presenter inside multi-author lists — exactly what
the OCR matcher must be robust to) + matching CSV; every title page was
offline-validated to match only its own schedule row (score 1.00, no
cross-matches).

## II.5 Web scenarios (W0–W6)

Setup: two real browsers with two different logged-in accounts on the
same talk — Edge (account A) on monitor 1, Firefox (account B) on
monitor 2 — user-prepared once; the harness binds them as actors.

| Wave | What it proves | Key evidence |
|---|---|---|
| `web_w0_smoke.yaml` | Actor model works; two distinct logins verified; slide navigation independent in both directions | assert_screen per actor |
| `web_w1_live.yaml` | Desktop presents live → **late joiner lands on the current slide** (not 1); auto-advance with LIVE badge; live audio after the "Listen Live" gesture (peak 0.84); `viewer_count ≥ 2`; end-of-talk → recorded state; the early joiner (hidden under the fullscreen presenter all talk) surfaces on the complete filmstrip | verify_audio_out, verify_cloud viewers |
| `web_w3_collaboration.yaml` | Group create in A → **AI reads the generated 8-char join code off A's screen** → typed into B → B joins → chat delivered **both ways** | DB: study_groups (2 members) + both message rows |
| `web_w3_whispers.yaml` | Private whisper sub-chat, member picker, both directions | DB: whisper, 2 members, 2 messages |
| `web_w3_annotations.yaml` | A draws ink (`draw` step); the stroke renders live in B (same group) | cross-browser assert |
| `web_w3_voice.yaml` | WebRTC mesh voice: both join ("Voice · 2 in call" both sides); piper TTS into the mic is **audible on the system output** — the TTS feeds only the loopback mic, so sink audio can only have crossed the mesh (peak 1.0 vs 0.000 when broken); clean leave | verify_audio_out |
| `web_w2_replay.yaml` | Self-contained: records its own throwaway narrated talk (fresh 1..N numbering), then: playback audible; **pause verified silent** (peak 0.000); marker walk while paused moves exactly +2/−1 slides; A unaffected | verify_audio_out min/max_peak |
| `web_w4_ai.yaml` | Gemini **region explain** (draw doubles as region drag) returns a real explanation; follow-up question answered; B's AI tab stays empty (per-user isolation); Translate dropdown renders **real French in-place** while B keeps English | cross-browser asserts |
| `web_w6_auth_lite.yaml` | Login cookies survive reload on both real accounts | assert_screen |
| `w6_auth_security.py` | Full auth security with throwaway accounts (Part I.3) | HTTP + DB |

W5 (quizzes/streaks/homework) is **N/A on the web** — that UI exists only
in the Android apps.

## II.6 Cost & performance profile

- 7–25 AI calls per scenario; ~5–15 s per call (CLI backend);
  full scenarios run 1–5 minutes wall-clock.
- `--replay` mode re-runs a scenario from the coordinate cache with
  **zero** AI calls (asserts still need the judge; pure click/type flows
  replay free).
- The locator runs on the developer's Claude subscription via `claude -p`
  — one session-limit exhaustion occurred at ~3 AM and reset on schedule;
  an `ANTHROPIC_API_KEY` switches it to metered API with no other change.

## II.7 How to run everything

```bash
# unit/integration suite (also runs in CI)
venv/bin/python3 -m pytest tests/ -q

# desktop GUI scenarios (screen must be hands-off while they run)
venv/bin/python3 -m tests_gui_agent.runner tests_gui_agent/scenarios/<name>.yaml
#   --replay          reuse cached coordinates (zero locate calls)
# artifacts: tests_gui_agent/runs/<timestamp>/report.html

# web scenarios: open the two browsers on the same talk first (two logins),
# then run web_w0_smoke.yaml … web_w4_ai.yaml as above

# auth security (throwaway accounts, self-purging)
SS_DBURL=<railway DATABASE_PUBLIC_URL> \
  venv/bin/python3 tests_gui_agent/w6_auth_security.py

# credit atomicity (SeenSlide repo; its venv has asyncpg)
cd ../SeenSlide && SS_DBURL=<url> \
  venv/bin/python3 testing_scripts/test_credit_transactions.py
```

The Railway DB URL comes from
`railway variables --service Postgres --environment production --kv`
(requires `railway login`).

---

# Part III — Results

## III.1 Bugs found, fixed, and shipped

Every bug below was discovered by the automated testing described above,
fixed, regression-covered where unit-testable, and deployed (desktop
v1.0.39/v1.0.40; backend deployed continuously).

| # | Found by | Bug | Impact | Fix |
|---|---|---|---|---|
| 1 | P1 (sandbox storage override didn't take) | `storage:` config section ignored by providers; `config.yaml` said `base_dir` (a key nothing read) → all slide data lived in **volatile `/tmp`**, wiped on reboot | Every real install lost local slides on reboot | StorageManager merges the section; `base_path` + expanduser + persistent default; one-time `/tmp` rescue migration with DB path rewrite (v1.0.39) + 3 regression tests |
| 2 | P2 (`verify_voice`: "0 markers") | SLIDE_UNIQUE→marker subscription existed only in the *cloud* branch of `start_voice_recording` | Local-only voice recordings could never be synced to slides | Subscribe unconditionally; flush queue gated on uploader; 2 regression tests |
| 3 | P3 (schedule looked empty after CSV import) | Conference talk-row inputs hardcoded `background: white` while dark theme's `TEXT_DARK` is `#ffffff` — white-on-white | Schedule text invisible in dark theme | Theme token `BG_WHITE` |
| 4 | P3 tightened oracle + user report ("non-slides uploaded") | Slide gate: base captured at countdown **end** (deck already fullscreen → gate learns garbage/abstains); X11 gate kept every frame whose focused window was SeenSlide itself — exactly the post-deck junk; gate off by default because of the first flaw | App screenshots uploaded to the audience deck | Base grabbed at countdown **start**; own-window frames fall through to the pixel taskbar gate; gate default ON (hidden slides recoverable via Sessions) |
| 5 | P3 `verify_cloud` (count 15 vs 9 local) | `cloud_sessions.total_slides` incremented on upload but **no delete path ever decremented** | Public viewer over-reported slide counts after conference transitions | `decrement_slide_count` (cache-aware) on all delete paths + recount backfill migration 046; harness now enforces `cloud == kept` with zero slack |
| 6 | P4a (Sessions detail: "No talks found") | `orchestrator.update_session()` updated every in-memory reference but never persisted the row; the lazy row-switch skipped because the collection picker had already set the value in memory → `sessions.cloud_session_id` stayed NULL | Sessions view empty for any collection-based talk (also the root cause of P1's "unreliable" cloud-code lookups) | Persist the row in `update_session` (v1.0.40) + 2 regression tests |
| 7 | W1 (`viewer_count 0` with 2 browsers attached) | `update_viewer_count` had **zero callers**; the viewer live-follows by REST polling, so no websocket existed to count | Viewer counts always 0 everywhere | Presence tracked from distinct slides-poll clients in a 60 s sliding window |
| 8 | W6 (auth probe hit a 500) | `CreditManager` + referral/access-key/donation managers each instantiated **their own never-connected `DatabaseManager()`** instead of the initialized singleton | `GET /api/credits/balance` → 500 for **every logged-in user**; all credit/referral/donation queries dead | Shared `lazy_db` proxy resolving `get_db()` at call time |
| 9 | Exposed by #8's fix | `db.transaction()` called at five sites but **the method didn't exist** — and inner `db.execute()` calls each grabbed separate pooled connections anyway | Credit grant/spend, referral completion, access-key spend, anon-account merge: erroring and non-atomic | Real `transaction()`: one connection bound via contextvar; `acquire()` prefers it, so nested manager calls join the transaction; commit/rollback; nested blocks join the outer. Verified on prod incl. rollback |
| 10 | Exposed by #9's fix (live probe: balance 40) | Welcome bonus granted twice — a direct row seed *plus* `add_credits`; while add_credits was broken the seed was accidentally the only grant | New accounts got 40 instead of 20 once #9 was fixed | Seed the account at 0; `add_credits` is the single source of the grant + its log. Verified live: 20, one tx row |

**Observations filed (not yet fixed):** replay slide-sync on *legacy*
talks whose slide numbers don't start at 1 (pre per-talk-numbering data);
a voice-chat participant whose mic device dies transmits silence with no
UI indication.

## III.2 What the effectiveness demonstrates

- **The bugs were integration bugs.** Not one of the ten was findable by
  the unit suite alone: they lived in config plumbing (#1), event-wiring
  branches (#2), theme × widget interaction (#3), compositor-timing (#4),
  cross-repo counter bookkeeping (#5), memory-vs-DB divergence (#6), and
  dead wiring that type-checks fine (#7, #8, #9). The GUI harness found
  them because it exercises the *same seams a user does* — and its hard
  oracles caught what looked fine on screen (#5's counts, #2's markers).
- **Bug cascades are real.** #8 → #9 → #10 is a chain where each fix
  exposed the next; only end-to-end verification after each fix (live
  probes with throwaway accounts) caught the follow-ons.
- **Vision-LLM perception is production-grade for this use.** Across
  ~30 scenario runs: no misclicks that damaged state; failures were
  overwhelmingly *correct* rejections (wrong oracle, real state drift, or
  a genuine bug). One flake pattern (a refused locate on a visible
  element, ~1 occurrence / hundreds of calls) is handled by a re-run
  policy.
- **The same harness spans surfaces nothing else covers uniformly**: a
  PyQt desktop app, a native GTK file dialog, browser chrome permission
  prompts, two different browsers side-by-side, WebRTC audio, and a live
  production backend — with one step vocabulary.

## III.3 Known limits

- Linux/X11 only today (xdotool + mss). Windows/macOS runs and the
  Wayland capture path remain untested by the harness.
- The harness shares the screen: runs need the monitor hands-off, and a
  human moving windows mid-run is the main environmental hazard
  (mitigated by `SEENSLIDE_TEST_ON_TOP`, window re-query per step, and
  actor self-verification).
- Locator latency (~5–15 s) makes real-time interaction tests (e.g.
  clicking during continuous playback) nondeterministic — design
  scenarios to pause first.
- Judgments are natural-language: an imprecise assert can pass for the
  wrong reason. The mitigation is the hard-oracle layer, which every
  scenario ends with.
