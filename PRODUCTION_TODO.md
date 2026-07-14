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
- [ ] **Slide-upload retry / offline outbox.** `cloud_provider.save_slide`
      uploads once; a network blip drops the slide from the cloud forever →
      silent holes in the viewer deck (`modules/storage/manager.py:344`).
      Add a persistent outbox + retry/backfill (mirror the voice uploader).
- [ ] **Conference mode: wire it or hide the tab.** Launch button is a no-op
      `# TODO` (`gui/windows/main_dashboard.py:1892`); the tab collects input
      that goes nowhere. Connect to `ConferenceLauncher`/admin server, or hide.

## 🟠 Important (before scaling users)

- [ ] **Make SQLite concurrency-safe.** Shared connection, `check_same_thread=
      False`, no lock / WAL / busy_timeout (`modules/storage/providers/
      sqlite_provider.py:58`) while multiple threads + servers write. Add
      `PRAGMA journal_mode=WAL`, `busy_timeout`, and a write lock.
- [ ] **File logging + crash reporting.** No file log handler (main app logs to
      discarded stdout; `core/models/config.py:69` `log_file` is unused), no
      `sys.excepthook`, no crash reporter → users can't send logs. Add a
      rotating file handler + global excepthook (consider Sentry).
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
- [ ] **Fix cv2 / adaptive-dedup packaging.** Excluded in the Linux spec, but
      hidden-imported (and not installed) on Win/macOS → adaptive dedup ships on
      no platform (`seenslide.spec:102`, `build_windows.bat`,
      `build_macos.sh:175`). Bundle cv2 or drop the adaptive strategy.

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
