"""Voice recorder — captures microphone audio during a talk session.

Records to WAV, tracks slide-change markers with timestamps, and
follows the same daemon pattern used by CaptureDaemon.
"""

import logging
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core.bus.event_bus import EventBus
from core.interfaces.events import Event, EventType

logger = logging.getLogger(__name__)

# Default recording settings
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS = 1
DEFAULT_DTYPE = "int16"  # 16-bit PCM


@dataclass
class SlideMarker:
    """Timestamp marking when a new slide appeared during recording."""
    slide_number: int
    timestamp_seconds: float
    created_at: float = field(default_factory=time.time)


class VoiceRecorder:
    """Records microphone audio to WAV, synchronised with slide capture.

    Lifecycle:
        recorder = VoiceRecorder(event_bus, output_dir, ...)
        recorder.start()          # begins capturing audio
        recorder.add_marker(3)    # slide 3 appeared at this moment
        recorder.stop()           # finalises WAV file
        print(recorder.output_path, recorder.markers)

    The recorder subscribes to SLIDE_UNIQUE events on the event bus
    and automatically adds markers when new slides are detected.
    """

    def __init__(
        self,
        event_bus: EventBus,
        output_dir: str,
        session_id: str = "",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        device: Optional[int] = None,
    ):
        self._event_bus = event_bus
        self._output_dir = Path(output_dir)
        self._session_id = session_id
        self._sample_rate = sample_rate
        self._channels = channels
        self._device = device  # None = system default mic

        # State
        self._recording = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Output
        self._output_path: Optional[Path] = None
        self._wave_file: Optional[wave.Wave_write] = None
        self._markers: List[SlideMarker] = []
        self._start_time: float = 0.0
        self._total_frames: int = 0
        self._slide_counter: int = 0

        # Chunk buffer for cloud upload
        self._chunk_buffer = bytearray()
        self._chunk_lock = threading.Lock()

        # Subscribe to slide events for auto-markers
        self._event_bus.subscribe(EventType.SLIDE_UNIQUE, self._on_slide_unique)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def output_path(self) -> Optional[str]:
        return str(self._output_path) if self._output_path else None

    @property
    def markers(self) -> List[SlideMarker]:
        return list(self._markers)

    @property
    def duration_seconds(self) -> float:
        if not self._recording:
            if self._total_frames and self._sample_rate:
                return self._total_frames / self._sample_rate
            return 0.0
        return time.time() - self._start_time

    def start(self) -> bool:
        """Start recording audio from the microphone."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.error(
                "sounddevice not installed — voice recording unavailable. "
                "Install with: pip install sounddevice"
            )
            self._publish_failed("sounddevice library not installed")
            return False

        if self._recording:
            logger.warning("Already recording")
            return False

        try:
            # Prepare output file
            self._output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"voice_{self._session_id}_{timestamp}.wav"
            self._output_path = self._output_dir / filename

            # Open WAV file
            self._wave_file = wave.open(str(self._output_path), "wb")
            self._wave_file.setnchannels(self._channels)
            self._wave_file.setsampwidth(2)  # 16-bit = 2 bytes
            self._wave_file.setframerate(self._sample_rate)

            # Reset state
            self._markers.clear()
            self._total_frames = 0
            self._slide_counter = 0
            self._start_time = time.time()
            self._recording = True
            self._paused = False

            # Start recording thread
            self._thread = threading.Thread(
                target=self._record_loop, daemon=True, name="voice-recorder"
            )
            self._thread.start()

            logger.info(f"Voice recording started: {self._output_path}")
            self._event_bus.publish(Event(
                EventType.VOICE_RECORDING_STARTED,
                data={
                    "session_id": self._session_id,
                    "output_path": str(self._output_path),
                    "sample_rate": self._sample_rate,
                },
                source="voice_recorder",
            ))
            return True

        except Exception as e:
            logger.error(f"Failed to start voice recording: {e}", exc_info=True)
            self._cleanup()
            self._publish_failed(str(e))
            return False

    def stop(self) -> Optional[str]:
        """Stop recording and finalise the WAV file.

        Returns:
            Path to the recorded WAV file, or None on failure.
        """
        if not self._recording:
            return None

        self._recording = False

        # Wait for recording thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        # Close WAV
        self._close_wave()

        duration = self.duration_seconds
        path = str(self._output_path) if self._output_path else None

        logger.info(
            f"Voice recording stopped: {duration:.1f}s, "
            f"{len(self._markers)} markers, {path}"
        )

        self._event_bus.publish(Event(
            EventType.VOICE_RECORDING_STOPPED,
            data={
                "session_id": self._session_id,
                "output_path": path,
                "duration_seconds": duration,
                "markers": len(self._markers),
            },
            source="voice_recorder",
        ))

        return path

    def pause(self):
        """Pause recording (audio frames are silently discarded)."""
        self._paused = True
        logger.info("Voice recording paused")

    def resume(self):
        """Resume recording after pause."""
        self._paused = False
        logger.info("Voice recording resumed")

    def add_marker(self, slide_number: int = 0):
        """Add a slide marker at the current recording position.

        Args:
            slide_number: The slide number that just appeared.
                         If 0, auto-increments from last marker.
        """
        if not self._recording:
            return

        if slide_number == 0:
            self._slide_counter += 1
            slide_number = self._slide_counter

        elapsed = time.time() - self._start_time
        marker = SlideMarker(
            slide_number=slide_number,
            timestamp_seconds=round(elapsed, 3),
        )
        self._markers.append(marker)

        logger.debug(f"Voice marker: slide {slide_number} at {elapsed:.1f}s")
        self._event_bus.publish(Event(
            EventType.VOICE_MARKER_ADDED,
            data={
                "slide_number": slide_number,
                "timestamp_seconds": marker.timestamp_seconds,
            },
            source="voice_recorder",
        ))

    def flush_chunk(self) -> bytes:
        """Return audio bytes accumulated since the last flush and clear the buffer.

        Used by the cloud uploader to grab new audio after each slide event.

        Returns:
            Raw PCM bytes (16-bit, mono, 44100 Hz) — empty bytes if nothing new.
        """
        with self._chunk_lock:
            if not self._chunk_buffer:
                return b""
            data = bytes(self._chunk_buffer)
            self._chunk_buffer.clear()
            return data

    def get_stats(self) -> Dict:
        """Return current recording statistics."""
        return {
            "recording": self._recording,
            "paused": self._paused,
            "duration_seconds": round(self.duration_seconds, 1),
            "markers": len(self._markers),
            "output_path": self.output_path,
            "sample_rate": self._sample_rate,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_loop(self):
        """Background thread: read audio from mic and write to WAV."""
        import sounddevice as sd

        block_size = 1024
        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype=DEFAULT_DTYPE,
                blocksize=block_size,
                device=self._device,
            ) as stream:
                while self._recording:
                    data, overflowed = stream.read(block_size)
                    if overflowed:
                        logger.debug("Audio buffer overflow (frames dropped)")
                    if self._paused:
                        continue  # Discard frames while paused
                    raw = data.tobytes()
                    with self._lock:
                        if self._wave_file:
                            self._wave_file.writeframes(raw)
                            self._total_frames += len(data)
                    with self._chunk_lock:
                        self._chunk_buffer.extend(raw)

        except Exception as e:
            logger.error(f"Voice recording loop error: {e}", exc_info=True)
            self._recording = False
            self._publish_failed(str(e))

    def _on_slide_unique(self, event: Event):
        """Auto-add a marker when a new unique slide is detected."""
        if self._recording and not self._paused:
            self.add_marker()

    def _close_wave(self):
        """Safely close the WAV file."""
        with self._lock:
            if self._wave_file:
                try:
                    self._wave_file.close()
                except Exception as e:
                    logger.warning(f"Error closing WAV file: {e}")
                finally:
                    self._wave_file = None

    def _cleanup(self):
        """Clean up on failure."""
        self._recording = False
        self._close_wave()

    def _publish_failed(self, reason: str):
        self._event_bus.publish(Event(
            EventType.VOICE_RECORDING_FAILED,
            data={"reason": reason, "session_id": self._session_id},
            source="voice_recorder",
        ))

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def list_audio_devices() -> List[Dict]:
        """List available audio input devices.

        Returns:
            List of dicts with 'index', 'name', 'channels', 'sample_rate'.
            Empty list if sounddevice is not installed.
        """
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            inputs = []
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0:
                    inputs.append({
                        "index": i,
                        "name": d["name"],
                        "channels": d["max_input_channels"],
                        "sample_rate": int(d["default_samplerate"]),
                    })
            return inputs
        except Exception:
            return []

    @staticmethod
    def is_available() -> bool:
        """Check if voice recording is available (sounddevice installed)."""
        try:
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            return False
