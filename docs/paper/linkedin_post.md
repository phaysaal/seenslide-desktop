# LinkedIn post — harness paper release

> Safe-to-publish check: no mention of the theory work, its language, its
> venue, or any submission. Purely the testing artifact + results.

---

## Main post

I asked an AI to test my app the way a human QA engineer would — mouse,
keyboard, eyes, ears — and it found 10 production bugs my 65-test unit
suite had no chance of catching.

Two design choices did the heavy lifting:

🧠 **Script as brain, LLM as eyes.** The test is a fixed, reviewable
script. The AI never decides what to do — it only *finds* elements from
plain-English descriptions, *judges* screens, and *reads* values off
pixels. Deterministic where it must be, intelligent where nothing else
works.

🔒 **A screen that merely looks right can't pass.** Every scenario ends
in oracles the model can't fool — database, cloud API, image hashing,
audio waveforms. 58 runs, zero false passes.

One harness, one step vocabulary: a native desktop app, two browsers
logged in as two different users, real slide decks, synthetic voice
crossing a live WebRTC call, network outages, and the production cloud.

The bugs? All integration bugs. Three weren't even visible on screen.

If you want the details — the architecture, the measured accuracy of the
vision layer, the full bug stories — knock me. Happy to share the paper
and talk shop.

Built on SeenSlide (my live presentation + study app), with Claude as
coding assistant and vision layer.

#SoftwareTesting #LLM #QA #TestAutomation #AIEngineering

---

## Optional "ghost" opener/closer

> A more personal framing — use as the opening hook OR the closing line.
> Turns the one real caveat (the harness owns the screen while it runs)
> into color instead of an apology.

**As an opener:**
The strangest part wasn't the bugs. It was watching a ghost do my job.
While I worked on something else, an AI drove my app end-to-end — clicking,
typing, presenting, listening — entirely on its own. The only rule: hands
off. It owns the screen while it runs, so I just... watched it work.

**As a closer:**
Honestly, the most memorable part was the feeling: a ghost quietly
doing my testing in the background while I did other things. (The one
catch — it owns the mouse and screen while running, so you really do have
to let it work.) Slightly eerie. Mostly wonderful.

## Posting notes

- Attach 1–2 images: a film-strip report step (red bounding box + click
  crosshair) is the most self-explanatory visual.
- The post intentionally has no link — "knock me" is the CTA. Have the
  PDF ready to send in DMs; add a link later if reach outgrows DMs.
- Timing: any time. Nothing here touches the theory line of work.
