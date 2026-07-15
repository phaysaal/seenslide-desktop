"""Synthetic voice for the GUI harness: TTS -> virtual microphone.

A pw-loopback pair (sink `ss-mic-in` -> device-class source "SS-Test-Mic")
is created and the source made the system DEFAULT for the duration of a run
(previous default saved and restored). Narration synthesized with piper-tts
is played into the sink side with pw-play — the app, recording from the
default microphone, hears a clean synthetic voice with zero physical audio
involved.

Why pw-loopback and not `pw-cli create-node` or a pw-play stream with
media.class=Audio/Source/Virtual: on this PipeWire, create-node silently
creates nothing, and wireplumber refuses to set a stream-class node as
default ("is not a device node"). The loopback's playback side is a proper
Audio/Source device node, which wpctl accepts. (pactl is not installed.)
"""
import contextlib
import logging
import re
import subprocess
import time
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
VOICE_MODEL = HERE / ".voices" / "en_US-lessac-medium.onnx"
MIC_SINK_NAME = "ss-mic-in"          # pw-play target (loopback capture side)
MIC_DESCRIPTION = "SS-Test-Mic"      # shows up in wpctl status Sources


class VirtualMic:
    """Lifecycle of the virtual microphone + default-source switcheroo."""

    def __init__(self):
        self.node_id = None
        self.prev_default_id = None
        self._loopback = None
        self._players = []

    # -- setup / teardown ------------------------------------------------

    def create(self):
        self._loopback = subprocess.Popen(
            ["pw-loopback",
             "--capture-props",
             f"{{ node.name={MIC_SINK_NAME} media.class=Audio/Sink "
             "audio.position=[MONO] }",
             "--playback-props",
             f'{{ node.name=ss-test-mic node.description="{MIC_DESCRIPTION}" '
             "media.class=Audio/Source audio.position=[MONO] }"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            time.sleep(0.4)
            self.node_id, self.prev_default_id = self._scan_sources()
            if self.node_id:
                break
        if not self.node_id:
            self.destroy()
            raise RuntimeError("virtual mic source did not appear in wpctl status")
        subprocess.run(["wpctl", "set-default", str(self.node_id)],
                       check=True, timeout=10)
        logger.info(f"virtual mic up (node {self.node_id}); previous default "
                    f"source was {self.prev_default_id}")

    def destroy(self):
        for p in self._players:
            if p.poll() is None:
                p.kill()
        self._players = []
        # Restore the user's real default mic FIRST — never leave their
        # system recording from a dead node.
        if self.prev_default_id:
            subprocess.run(["wpctl", "set-default", str(self.prev_default_id)],
                           timeout=10)
            logger.info(f"default source restored to {self.prev_default_id}")
            self.prev_default_id = None
        if self._loopback and self._loopback.poll() is None:
            self._loopback.terminate()
            try:
                self._loopback.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._loopback.kill()
        self._loopback = None
        self.node_id = None

    def _scan_sources(self):
        """(virtual mic node id or None, current default source id or None)
        from the Sources block of wpctl status."""
        out = subprocess.run(["wpctl", "status"], capture_output=True,
                             text=True, timeout=10).stdout
        try:
            block = out.split("Sources:")[1].split("Source endpoints:")[0]
        except IndexError:
            return None, None
        mine = re.search(r"(\d+)\.\s+" + re.escape(MIC_DESCRIPTION), block)
        default = re.search(r"\*\s+(\d+)\.", block)
        return (mine.group(1) if mine else None,
                default.group(1) if default else None)

    # -- playback ----------------------------------------------------------

    def play(self, wav_path: str):
        """Feed a WAV into the virtual mic (async)."""
        p = subprocess.Popen(
            ["pw-play", "--target", MIC_SINK_NAME, wav_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._players.append(p)
        return p


# ---------------------------------------------------------------------------
# Narration synthesis
# ---------------------------------------------------------------------------

def _page_sentence(doc, i: int) -> str:
    """A short spoken line for page i, seeded with the page's own text."""
    words = doc[i].get_text().split()[:12]
    snippet = " ".join(w for w in words if w.isprintable())
    return f"Slide {i + 1}. {snippet}." if snippet else f"Slide {i + 1}."


def build_narration(pdf_path: str, out_wav: str, pages: int,
                    hold_first: float, interval: float) -> str:
    """One WAV timeline: page k's line starts when page k is on screen,
    padded with silence to the presentation schedule."""
    import fitz
    from piper import PiperVoice

    voice = PiperVoice.load(str(VOICE_MODEL))
    doc = fitz.open(pdf_path)
    n = min(pages, doc.page_count) if pages else doc.page_count

    rate, width, channels = 22050, 2, 1

    def synth(text: str) -> bytes:
        tmp = out_wav + ".part.wav"
        with wave.open(tmp, "wb") as w:
            voice.synthesize_wav(text, w)
        with contextlib.closing(wave.open(tmp)) as w:
            return w.readframes(w.getnframes())

    frames = bytearray()
    for i in range(n):
        slot = hold_first if i == 0 else interval
        spoken = synth(_page_sentence(doc, i))
        slot_bytes = int(rate * slot) * width * channels
        if len(spoken) > slot_bytes:
            spoken = spoken[:slot_bytes]          # never overrun the slot
        frames += spoken
        frames += b"\x00" * (slot_bytes - len(spoken))  # pad slot with silence

    with wave.open(out_wav, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    dur = len(frames) / (rate * width * channels)
    logger.info(f"narration built: {out_wav} ({dur:.1f}s, {n} pages)")
    return out_wav


def wav_stats(path: str):
    """(duration_seconds, peak_amplitude 0..1) — proves audio actually flowed."""
    import audioop
    with contextlib.closing(wave.open(path)) as w:
        frames = w.readframes(w.getnframes())
        dur = w.getnframes() / w.getframerate()
        peak = audioop.max(frames, w.getsampwidth()) / 32768.0 if frames else 0.0
    return dur, peak
