# Web Viewer Test Plan — two-browser collaboration E2E

Goal: extend the vision-driven GUI harness to the **audience side**: two
browsers (viewer A and viewer B), different logins, same session — verify
everything a real audience does, with the desktop app as the live source
where needed.

The harness pieces already exist and are browser-agnostic: xdotool input,
AI locator (claude-opus-4-8), YAML runner, virtual-mic audio, HTTP relay,
psql access to the production DB for hard oracles. What's new is a
**two-actor model**: every interactive step gains a `target: A|B`.

---

## 0. Harness extensions (W0)

| Piece | Design |
|---|---|
| Browser actors | Two Chromium/Chrome instances, separate `--user-data-dir` profiles (A, B), placed left/right half of the primary monitor via `--window-position/--window-size` |
| Targeted steps | `click/type/key/assert_screen` gain `target: A\|B` — screenshot is cropped to that browser's window rect (xdotool geometry), so the locator sees one viewer at a time and coordinates stay unambiguous |
| Logins | Two persistent test accounts (throwaway email/phone + PIN, purged afterwards like the desktop ones). Profiles keep cookies, so login happens once in a setup scenario and later runs reuse the profiles |
| Audio in | The existing pw-loopback virtual mic is the system default — whichever browser has mic permission records synthetic speech. One-speaker-at-a-time is enough for voice-chat tests |
| Audio out (proof) | `pw-record --target <sink monitor>` captures what the browsers PLAY — peak analysis proves live audio / replay audio / voice chat actually produced sound, same trick as verify_voice |
| DB oracles | `verify_pg` step: read-only SQL against production (messages, strokes, quiz completions, streaks rows) via the railway DATABASE_PUBLIC_URL |
| Live source | Existing desktop scenarios (present_pdf + narration) create the live session; `show_cloud_code` hands the code to the browser steps |

**W0 exit criterion (smoke):** both browsers open `seenslide.com/<code>`
of a finished talk, both render slide 1, logins verified as two distinct
account names on screen.

---

## 1. W1 — Live talk following (desktop presents, both browsers watch)

| # | Test | Oracle |
|---|---|---|
| 1.1 | Slide auto-advance: desktop presents 6 pages with narration; both browsers follow | assert_screen per browser at two checkpoints: same slide as the presenter (crop-match) |
| 1.2 | Live audio | pw-record of browser output during the talk → peak > threshold |
| 1.3 | Viewer count | presenter side / API shows 2 viewers while both browsers attached |
| 1.4 | Late joiner | browser B joins mid-talk → lands on the CURRENT slide, not slide 1 |
| 1.5 | Detach/re-follow | A scrolls back two slides (unfollows), live badge indicates detached; "jump to live" returns to current |
| 1.6 | End of talk | both browsers transition to the recorded/complete state; slide count matches deck |

## 2. W2 — Recorded replay (voice-synced)

| # | Test | Oracle |
|---|---|---|
| 2.1 | Voice replay: play recording in A | audio out peak > threshold; play/pause UI state |
| 2.2 | Slide sync on seek: seek into talk middle | the slide shown matches the marker for that timestamp (verify_pg: voice_slide_markers) |
| 2.3 | Marker walk: next/prev slide during playback jumps audio | position changes consistent with markers |
| 2.4 | Talking-chalkboard replay: a talk with ink annotations replays strokes in time with audio | strokes appear progressively (two screenshots, stroke count grows) |

## 3. W3 — Collaboration (study groups, the core two-user wave)

| # | Test | Oracle |
|---|---|---|
| 3.1 | A creates a study group on the session; B joins by code/invite | group visible in both; verify_pg: study_groups + 2 members |
| 3.2 | Chat A→B and B→A | message typed in A appears in B (assert_screen B) and vice versa; verify_pg: study_group_messages rows |
| 3.3 | Whisper channel: A whispers to B | whisper visible ONLY in the channel view; verify_pg: study_group_whisper_messages |
| 3.4 | Shared annotation: A draws on slide 3 | stroke renders in B on the same slide (assert_screen); verify_pg: study_group_strokes |
| 3.5 | Annotation + voice (chalkboard live): A draws while speaking (virtual mic) | B sees ink; recording row exists (talk_stroke_recordings) |
| 3.6 | Group voice chat (WebRTC mesh): A joins voice, B joins voice; A speaks via virtual mic | B shows A's speaking indicator; audio-out capture at B has peak; leaving tears down cleanly |
| 3.7 | File share in group (if UI exposes it) | file sent by A downloadable in B; verify_pg: study_group_files |
| 3.8 | Membership boundary: a third profile NOT in the group must not see messages/strokes | assert_screen on fresh profile |

## 4. W4 — Personal features + AI (per-user isolation matters)

| # | Test | Oracle |
|---|---|---|
| 4.1 | Private notes: A writes a note on slide 2 | note persists for A after reload; **B never sees it**; verify_pg: user_notes owner |
| 4.2 | Saved slides: A saves slide 4 | appears in A's saved list only |
| 4.3 | AI chat about a slide (Gemini) | answer text renders; verify_pg: ai_conversations row for A only |
| 4.4 | Region AI query: A selects a slide region and asks | region + answer render; cloud_ai_regions row |
| 4.5 | Live captions (Groq transcription) during a narrated live talk | caption text appears and roughly matches the narration script |
| 4.6 | In-place slide translation | translated slide renders in A; B still sees the original; slide_translations row |
| 4.7 | Voice translation (GROQ-gated) | translated audio plays (audio-out peak) |
| 4.8 | Quota/credits: AI usage decrements visible credits | verify_pg: user_credits/key_ai_usage delta |

## 5. W5 — Quizzes, streaks, homework

| # | Test | Oracle |
|---|---|---|
| 5.1 | Quiz on a talk: A takes it (some right, some wrong), B takes it independently | score screens differ as expected; verify_pg: talk_quiz_completions two rows |
| 5.2 | Quiz isolation: B's answers not visible to A | UI check |
| 5.3 | Streak increments after activity | verify_pg: user_streaks row for each |
| 5.4 | Homework flow (assign/submit if UI exposes both sides) | submitted state in both views |
| 5.5 | Push opt-in prompt behavior | UI-only check (actual push delivery out of scope) |

## 6. W6 — Auth + access control

| # | Test | Oracle |
|---|---|---|
| 6.1 | Sign-in with wrong PIN 3×: lockout messaging | secret_failed_attempts increments (verify_pg), lock clears after window |
| 6.2 | Private session with access key: no key → blocked; with key → in | HTTP + UI |
| 6.3 | Session persistence: reload keeps login (cookie) | UI |
| 6.4 | Sign-out from A doesn't affect B | UI both |

---

## Sequencing

1. **W0** harness extension + smoke (browser actors, target crops, login-once setup scenario)
2. **W1** live following (reuses desktop P2-live scenario as the source)
3. **W3** collaboration — the highest-value two-user wave, and the user's headline ask
4. **W2** replay, **W4** AI/personal, **W5** gamification, **W6** auth — in that order
5. Cleanup scenario: purge the two test accounts + their groups/messages (same railway psql path as the desktop purge)

## Needed from the user

- Which two browsers (two Chrome profiles is simplest; Chrome + Firefox also possible, slightly more locator variance)
- Two test logins — or approval for me to register two throwaway accounts (email+PIN or phone+PIN) that get purged afterwards
- Confirmation that GROQ/Gemini API keys are live in production (AI tests) and whether any feature is behind `is_tester`
- Screen budget: each wave needs the monitor hands-off like the desktop runs (browsers side-by-side on the primary)
