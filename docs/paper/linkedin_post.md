# LinkedIn post — harness paper release

> Safe-to-publish check: no mention of the theory work, its language, its
> venue, or any submission. Purely the testing artifact + results.

---

## Main post

I asked an AI to test my app the way a human QA engineer would — mouse,
keyboard, eyes, ears — and it found 10 production bugs my 65-test unit
suite had no chance of catching.

Here's the design idea, because I think it matters more than the bug count:

🧠 **Script as brain, LLM as eyes.**
Most "AI testing agents" explore your app and improvise. That's the wrong
property for a regression test — an improvising agent never runs the same
test twice. So I inverted it: the test is a fixed, reviewable script, and
the LLM does exactly three things: FIND an element from a plain-English
description ("the red End Presentation button"), JUDGE a screen ("does
this show a live talk with a LIVE badge?"), and READ a value off the
pixels (an 8-character invite code on one browser, typed into another).
It never decides what to do next.

🔒 **A screen that merely looks right can't pass.**
Every scenario ends in oracles the model can't fool: database queries,
the public cloud API, perceptual image hashing against the source PDF,
audio waveform analysis. Result: across a 58-run campaign, zero false
passes. When the vision model was wrong, the test aborted loudly instead
of lying quietly.

What one harness ended up covering, with a single step vocabulary:
▪ a native desktop app (PyQt), including the native GTK file dialog
▪ two different real browsers side-by-side, logged in as two different users
▪ a synthetic "presenter" playing real slide decks fullscreen
▪ an OS-level virtual microphone — TTS speech goes in, crosses a real
  WebRTC voice call, and is verified as a waveform at the speaker output
▪ a network that dies mid-talk (and a product that heals when it returns)
▪ the live production backend

And because instruments deserve calibration: measured from the campaign's
own artifacts, the vision layer ran at ≥97.6% true-accept on screen
judgments, ≥97.5% per-call element-find rate (100% after retries), ~9s
median latency, ~10 model calls per scenario.

The 10 bugs were all integration bugs — silent data loss to /tmp, a
counter no code path ever decremented, an API 500-ing for every logged-in
user, a three-bug cascade where each fix exposed the next. Not one was
visible to unit tests. Three weren't even visible on screen.

Paper draft (architecture, methodology rules learned from failures, full
bug inventory): [LINK]

Built on SeenSlide (my slide-sharing side project), together with Claude
as the coding assistant and the vision layer.

#SoftwareTesting #LLM #QA #TestAutomation #AIEngineering #GUITesting

---

## Short alternative (if the long one feels heavy)

An AI tested my app end-to-end — desktop, two browsers, live audio over
WebRTC, network outages, production cloud — and found 10 bugs my unit
tests couldn't see.

The trick isn't a smarter agent. It's a dumber one:
• the test is a fixed script (reviewable, repeatable)
• the LLM only finds, judges, and reads — never decides
• the verdict comes from database/API/audio oracles, never from "the
  screen looks right"

58 runs, zero false passes. Measured vision-layer accuracy in the paper:
[LINK]

#SoftwareTesting #LLM #TestAutomation

---

## Posting notes

- Attach 1–2 images: the film-strip report screenshot (a step with the
  red bounding box + click crosshair) is the most self-explanatory
  visual; the measured-operating-point table is a good second.
- If people ask "is this open source?" — decide before posting; the
  honest current answer is "the harness lives inside the product repo;
  paper describes it fully enough to rebuild."
- Timing: any time. This post deliberately contains nothing about the
  theory line of work.
