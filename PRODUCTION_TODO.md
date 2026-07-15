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
- [ ] **DB backups + corruption recovery.** A corrupt `seenslide.db` = total
      local data loss. Add `PRAGMA integrity_check` on open + periodic backup.
- [ ] **Automated test suite + CI gate.** ~20 ad-hoc manual scripts, no
      framework, nothing runs in CI. Unit-test dedup + storage at minimum; add
      a test job to the release workflow.
- [ ] **First-run privacy consent.** Cloud slide upload is ON by default
      (`config/config.yaml:104`) with no in-app disclosure. Add a first-run
      consent / opt-in.
- [ ] **Fix credential storage claims + transport hardening.** Plaintext
      fallback is mislabeled "encrypted" (`core/session/credential_manager.py:
      33,60`); 30-day bearer stored cleartext when keyring unavailable. Encrypt
      or correct the claim; reject non-`https` `api_url`
      (`core/identity.py:196-206`).
- [x] **Fix cv2 / adaptive-dedup packaging.** cv2 now ships on every platform:
      rapidocr-onnxruntime (conference auto-advance OCR) depends on
      opencv-python, the Linux spec no longer excludes cv2, and all three
      builds collect rapidocr's models + onnxruntime libs. (v1.0.37)

## 🟡 Polish / product decisions

- [ ] **Settings/Preferences screen.** Capture interval, provider, voice
      quality/device, cloud on/off are file-only. Also fix config drift:
      `config_loader.load_defaults()` disagrees with `config.yaml`
      (provider/strategy).
- [ ] **Monetization enforcement** (only if paid tiers are a launch
      requirement). `account_tier` is defined but never read
      (`core/identity.py:155`); everything is open.
- [ ] **Surface Direct-Talk start failures.** No dialog if capture backend or
      voice fails to init (`gui/windows/main_dashboard.py:3620,3740`).
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
