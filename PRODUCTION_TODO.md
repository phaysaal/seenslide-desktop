# SeenSlide Desktop — Production Readiness TODO

Tracking the gaps found in the production-readiness review (2026-07-14).
Status: the core happy path (capture → dedup → local store → cloud sync →
viewer + voice) works well; these items are the "last 20%" for a public,
paid-grade release. Ordered by severity within each tier.

Legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## 🔴 Blockers (before any public release)

- [ ] **Sign + notarize installers.** macOS signs only if `CODESIGN_IDENTITY`
      is set and never notarizes (`packaging/build_macos.sh:211-219`); Windows
      has no signing. → Gatekeeper / SmartScreen "unknown developer" blocks.
      Add signing + `notarytool` stapling; pass secrets in CI
      (`.github/workflows/build-release.yml`).
- [ ] **Secure the update path.** Integrity is a SHA-256 from the same server
      response, no code signature / pinning (`core/updater/downloader.py:71`) →
      MITM/compromised server = RCE. Add signature verification. Also make
      "Install & restart" actually self-update + restart instead of `xdg-open`
      (`core/updater/update_banner.py:297-320`).
- [x] **Slide-upload retry / offline outbox.** Failed uploads now queue in a
      SQLite `upload_outbox`; a background worker retries every 30s and
      backfills across restarts (drops on 404 / missing image / 100 attempts /
      7 days). Verified with a mocked cloud. (commit `084b493`)
- [x] **Conference mode: wired.** Launch now creates a dedicated cloud
      collection, runs the talk schedule sequentially through the live
      pipeline (per-talk cloud talk, voice recording, dedup scope, slide
      numbering), with a "Next Talk ▸" button + progress chip in the live
      view; End ends the conference. Also fixed the never-set `is_active`
      guard. (this commit)

## 🟠 Important (before scaling users)

- [x] **Make SQLite concurrency-safe.** WAL + busy_timeout=5000 +
      synchronous=NORMAL; all writes serialized through a `_write()` lock with
      commit/rollback (multi-statement deletes now atomic). Verified with a
      6-thread concurrency test. (commit `02d5bcf`)
- [x] **File logging + crash reporting.** `core/logging_setup.py`: rotating
      file log (2MB×3, utf-8) in a platform log dir + `sys.excepthook` (Qt
      slots) + `threading.excepthook`. Verified. Sentry still optional/open.
      (commit `2c11d1f`)
- [x] **DB backups + corruption recovery.** quick_check at open; a corrupt db
      is moved aside (kept for forensics) and the last-known-good backup
      restored, or a fresh db created. Backup refreshed at open + close via
      SQLite's online backup API. Tested (garbage db -> data restored).
- [x] **Automated test suite + CI gate.** tests/ with 49 pytest tests covering
      dedup (tiled diff, per-talk reset, injection), upload outbox, SQLite
      concurrency/rollback, title matcher (real OCR fixtures), CSV schedule
      parser, blank-frame guard. CI: tests.yml on push/PR + a test job gating
      all three release builds. Still open: GUI-level tests, coverage growth.
- [x] **First-run privacy consent.** One-time dialog on first launch:
      "Enable cloud sync" vs "Local only"; the choice persists and the
      orchestrator disables the cloud provider when declined.
- [x] **Credential storage claims + transport hardening.** Docstrings now
      state the fallback is plaintext+0o600 (not "encrypted"); non-https
      api_url rejected (localhost allowed for dev, tested); secret files
      (.credentials.json, .device_id, .identity.json, .jwt_secret) are
      created 0o600 atomically — chmod race closed. Real at-rest encryption
      of the fallback remains open.
- [x] **Fix cv2 / adaptive-dedup packaging.** cv2 now ships on every platform:
      rapidocr-onnxruntime (conference auto-advance OCR) depends on
      opencv-python, the Linux spec no longer excludes cv2, and all three
      builds collect rapidocr's models + onnxruntime libs. (v1.0.37)

## 🟡 Polish / product decisions

- [ ] **Conference transitions leave already-uploaded tail slides in the
      cloud.** `_conf_remove_trigger_slide` deletes the transition tail from
      the old talk locally, but frames uploaded before the deletion stay in
      the cloud session (~+2 slides per auto-advance; observed in harness
      runs JJY-8540/DXJ-2040). Needs a cloud-side delete when removing the
      local tail.
- [x] **Settings/Preferences screen.** New sidebar Settings page: theme,
      capture backend + interval, slide filtering, microphone picker (by
      name, index-shift safe), image quality, cloud sync on/off (gives the
      consent choice a changeable home), log-folder button + version.
      Config drift fixed: load_defaults() now matches config.yaml
      (auto/perceptual/0.95/jpeg_quality) with a drift-guard test.
- [ ] **Monetization enforcement** (only if paid tiers are a launch
      requirement). `account_tier` is defined but never read
      (`core/identity.py:155`); everything is open.
- [x] **Surface Direct-Talk start failures.** Dialogs for: capture engine
      failed to initialize (was a silent log), Start clicked before the
      engine is ready (was a dead button), and voice/mic failure at talk
      start (talk continues, presenter warned).
- [ ] **Keyboard shortcuts + accessibility** in the main UI (stop-talk/Esc,
      tooltips, accessible names).
- [ ] **Remove dead legacy windows** (`ModeSelector`, `DirectTalkWindow`,
      `TalkManagerWindow`, collection dialogs) to cut maintenance risk.
- [ ] **Trim bundle size.** rapidocr pulls full `opencv-python` (~190MB
      uncompressed; headless would save ~130MB) — install rapidocr's deps in a
      controlled way (headless cv2) in the build envs. scipy (~73MB, pulled by
      imagehash but unused by dhash) is another candidate.
- [ ] **Minor:** emoji log lines can throw `UnicodeEncodeError` on some Windows
      consoles; write-then-chmod race on secret files; error responses logged
      verbatim (`cloud_provider.py`) — add redaction.
- [ ] **Verify the Windows window-state backend** on a real Windows build
      (maximized/fullscreen filtering) — implemented but not yet run on Windows.
- [ ] **Slide data lives in volatile /tmp/seenslide** (found by the GUI test
      harness): the `storage:` config section was ignored (fixed —
      StorageManager now merges it over the provider config), but
      `config.yaml` still says `base_dir` (a key providers never read) so real
      installs fall back to /tmp — **all local slides are lost on reboot**.
      Fix: `base_path: ~/.local/share/seenslide` + expanduser in providers +
      a one-time migration of existing /tmp data.

## Suggested order to production
1. Signing + notarization (unblocks distribution)
2. Slide-upload outbox (no more viewer holes)
3. SQLite WAL + lock · file logging + excepthook · DB backup (supportability)
4. Wire or hide Conference · first-run consent
5. Update signature verification + real self-update/restart
6. Test suite + CI gate

---

## ✅ Done
- [x] **User-controllable slide image quality** — Setup → Image quality slider
      (40–95%, Low/Medium/High/Maximum), persisted + applied live and at talk
      start; `storage.jpeg_quality` in config (commit `ea4cada`).
