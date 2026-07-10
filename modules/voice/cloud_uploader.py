"""Uploads voice audio chunks to the cloud backend during a talk.

Each PCM chunk is converted to OGG/Opus via ffmpeg before uploading,
reducing bandwidth ~10x (86 KB/s raw → ~8 KB/s Opus). If ffmpeg is
not available, falls back to uploading raw PCM.

All uploads go through a single worker thread draining a FIFO queue:
chunk order on the server is guaranteed by (a) uploading strictly
sequentially and (b) sending an explicit client-side chunk index that
the server uses to name the chunk file. Earlier versions spawned one
thread per chunk — a slow ffmpeg encode or a retry backoff let later
chunks overtake earlier ones, and the server (which numbered chunks
by arrival) merged them out of order.

Server stores each chunk as a separate .ogg file and concatenates
them into a single file when the recording stops.
"""

import io
import logging
import queue
import shutil
import subprocess
import threading
import time
from typing import Callable, List, Optional

import requests

logger = logging.getLogger(__name__)

# Check once at import time
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _pcm_to_opus(pcm_data: bytes, sample_rate: int = 44100, channels: int = 1) -> Optional[bytes]:
    """Convert raw PCM bytes to OGG/Opus using ffmpeg.

    Args:
        pcm_data: Raw 16-bit signed little-endian PCM.
        sample_rate: Sample rate in Hz.
        channels: Number of audio channels.

    Returns:
        OGG/Opus bytes, or None if conversion fails.
    """
    if not FFMPEG_AVAILABLE:
        return None

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "s16le",          # input: raw PCM 16-bit signed LE
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-i", "pipe:0",         # read from stdin
                "-c:a", "libopus",
                "-b:a", "64k",          # 64 kbps — good quality for voice
                "-f", "ogg",            # output: OGG container
                "pipe:1",               # write to stdout
            ],
            input=pcm_data,
            capture_output=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout:
            ratio = len(pcm_data) / len(result.stdout) if result.stdout else 0
            logger.debug(
                f"Opus conversion: {len(pcm_data)} → {len(result.stdout)} bytes "
                f"({ratio:.1f}x compression)"
            )
            return result.stdout
        else:
            logger.warning(f"ffmpeg failed: {result.stderr.decode()[:200]}")
            return None

    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timed out during Opus conversion")
        return None
    except Exception as e:
        logger.warning(f"Opus conversion failed: {e}")
        return None


class VoiceCloudUploader:
    """Uploads voice chunks + markers to the SeenSlide cloud backend.

    Converts PCM → OGG/Opus before uploading if ffmpeg is available.
    Falls back to raw PCM upload if not.
    """

    def __init__(
        self,
        api_url: str,
        session_token: str = "",
        sample_rate: int = 44100,
        channels: int = 1,
        slide_id_resolver: Optional[Callable[[int], Optional[str]]] = None,
    ):
        self._api_url = api_url.rstrip("/")
        # An explicit token wins (mostly for tests). Otherwise _headers reads
        # the live token from core.identity on every request, so token rotation
        # (sign-in, claim/merge, logout) takes effect mid-recording.
        self._session_token_override: Optional[str] = session_token or None
        # Pass the recorder's actual sample rate / channel count through to
        # ffmpeg. Hardcoding 44100 here used to cause pitch-shifted live
        # streams whenever the device's default rate diverged (48000 USB
        # mics, 16000 cheap headsets).
        self._sample_rate = int(sample_rate) if sample_rate else 44100
        self._channels = int(channels) if channels else 1
        # Maps a slide_number to its stable cloud slide_id (if the slide
        # upload has completed by marker time). Best-effort — markers fall
        # back to slide_number resolution server-side when this returns None.
        self._slide_id_resolver = slide_id_resolver
        self._recording_id: Optional[str] = None
        self._use_opus = FFMPEG_AVAILABLE

        # Ordered upload pipeline. _index_lock guards _chunk_index so the
        # index (which fixes audio order on the server) is assigned at
        # enqueue time, in flush order — never in upload-completion order.
        self._queue: "queue.Queue" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._worker_stop = threading.Event()
        self._index_lock = threading.Lock()
        self._chunk_index: int = 0

        if self._use_opus:
            logger.info(
                f"Voice upload: ffmpeg found — will compress to Opus "
                f"({self._sample_rate} Hz, {self._channels}ch, ~10x smaller)"
            )
        else:
            logger.info(
                f"Voice upload: ffmpeg not found — uploading raw PCM "
                f"({self._sample_rate} Hz, {self._channels}ch)"
            )

    @property
    def _headers(self) -> dict:
        """Authorization header from live identity (or override if set).

        Returns an empty dict when no token is available, so requests don't
        ship a bogus `Authorization: ""` that confuses the server.
        """
        token = self._session_token_override
        if not token:
            try:
                from core.identity import identity
                token = identity().token or ""
            except Exception:
                token = ""
        return {"Authorization": f"Bearer {token}"} if token else {}

    @property
    def recording_id(self) -> Optional[str]:
        return self._recording_id

    # ------------------------------------------------------------------
    # Cloud recording lifecycle
    # ------------------------------------------------------------------

    def start_cloud_recording(
        self, cloud_session_id: str, audio_format: str = None, talk_id: str = None
    ) -> bool:
        """Tell the cloud to create a new voice recording entry."""
        try:
            fmt = "ogg" if self._use_opus else "wav"
            params = {
                "audio_format": fmt,
                # The server needs the true capture rate to synthesize a
                # correct WAV header for raw-PCM playback (no-ffmpeg path)
                # and to store honest metadata for the OGG path.
                "sample_rate": self._sample_rate,
                "channels": self._channels,
            }
            if talk_id:
                params["talk_id"] = talk_id

            resp = requests.post(
                f"{self._api_url}/api/voice/desktop/start/{cloud_session_id}",
                params=params,
                headers=self._headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._recording_id = data.get("recording_id")
                with self._index_lock:
                    self._chunk_index = 0
                self._start_worker()
                logger.info(f"Cloud voice recording started: {self._recording_id} (format: {fmt})")
                return True
            else:
                logger.warning(f"Failed to start cloud voice recording: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Cloud voice start failed: {e}")
            return False

    def upload_chunk(self, pcm_data: bytes, slide_number: int = 0, timestamp_seconds: float = 0.0):
        """Queue an audio chunk for ordered background upload."""
        if not self._recording_id or not pcm_data:
            return
        with self._index_lock:
            self._chunk_index += 1
            index = self._chunk_index
        self._queue.put((index, pcm_data, slide_number, timestamp_seconds))

    def upload_chunk_blocking(self, pcm_data: bytes, slide_number: int = 0, timestamp_seconds: float = 0.0):
        """Queue the final audio chunk and wait until the queue is drained."""
        if not self._recording_id or not pcm_data:
            return
        self.upload_chunk(pcm_data, slide_number, timestamp_seconds)
        self.drain(timeout=90.0)

    def drain(self, timeout: float = 90.0) -> bool:
        """Wait until every queued chunk has been uploaded (or timeout).

        Returns True if the queue emptied in time.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.2)
        logger.warning(
            f"Voice upload queue did not drain within {timeout:.0f}s "
            f"({self._queue.unfinished_tasks} chunks outstanding)"
        )
        return False

    def sync_markers(self, markers: List) -> bool:
        """Replace the recording's auto markers with the authoritative list.

        Called at talk end with the recorder's full local marker list. The
        per-chunk marker POSTs during the talk are best-effort (single
        attempt, can be lost to network blips); this bulk PUT reconciles
        the cloud with what the recorder actually observed.

        Args:
            markers: list of objects with .slide_number and .timestamp_seconds
                     (modules.voice.recorder.SlideMarker).

        Returns:
            True on success.
        """
        if not self._recording_id or not markers:
            return False
        payload = []
        for m in markers:
            entry = {
                "slide_number": m.slide_number,
                "timestamp_seconds": m.timestamp_seconds,
            }
            slide_id = self._resolve_slide_id(m.slide_number)
            if slide_id:
                entry["slide_id"] = slide_id
            payload.append(entry)
        for attempt in range(3):
            try:
                resp = requests.put(
                    f"{self._api_url}/api/voice/desktop/markers/{self._recording_id}",
                    json={"markers": payload},
                    headers=self._headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    logger.info(f"Voice markers reconciled: {len(payload)} markers")
                    return True
                logger.warning(f"Marker sync failed: {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Marker sync attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(3)
        return False

    def stop_cloud_recording(self, duration_seconds: float = 0.0):
        """Finalize the cloud recording (drains pending chunks first)."""
        if not self._recording_id:
            self._stop_worker()
            return

        self.drain(timeout=90.0)
        try:
            resp = requests.post(
                f"{self._api_url}/api/voice/desktop/stop/{self._recording_id}",
                params={"duration_seconds": duration_seconds},
                headers=self._headers,
                timeout=30,
            )
            if resp.status_code == 200:
                logger.info(f"Cloud voice recording stopped: {self._recording_id}")
            else:
                logger.warning(f"Failed to stop cloud voice: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Cloud voice stop failed: {e}")
        finally:
            self._recording_id = None
            self._stop_worker()

    def upload_final_ogg(self, wav_path: str, recording_id: str, duration_seconds: float = 0.0):
        """Convert local WAV → OGG/Opus and upload as the final recording.

        This replaces the chunked data on the server with a single proper
        OGG file that has correct duration and is fully seekable.

        Args:
            wav_path: Path to local WAV file.
            recording_id: Cloud recording ID.
            duration_seconds: Total duration.
        """
        if not FFMPEG_AVAILABLE:
            logger.info("ffmpeg not available — skipping final OGG upload")
            return

        import tempfile
        import os

        ogg_path = None
        try:
            # Convert WAV → OGG/Opus
            ogg_fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
            os.close(ogg_fd)

            logger.info(f"Converting {wav_path} → OGG/Opus for final upload...")
            result = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-y",
                    "-i", wav_path,
                    "-c:a", "libopus", "-b:a", "64k",
                    ogg_path,
                ],
                capture_output=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.warning(f"Final OGG conversion failed: {result.stderr.decode()[:200]}")
                return

            ogg_size = os.path.getsize(ogg_path)
            wav_size = os.path.getsize(wav_path)
            logger.info(
                f"Converted: {wav_size} bytes WAV → {ogg_size} bytes OGG "
                f"({wav_size / ogg_size:.1f}x compression)"
            )

            # Upload as final file replacement
            with open(ogg_path, "rb") as f:
                files = {
                    "file": ("final.ogg", f, "audio/ogg"),
                }
                resp = requests.post(
                    f"{self._api_url}/api/voice/desktop/upload-final/{recording_id}",
                    files=files,
                    params={"duration_seconds": duration_seconds},
                    headers=self._headers,
                    timeout=120,
                )

            if resp.status_code == 200:
                logger.info(f"Final OGG uploaded: {recording_id} ({ogg_size} bytes)")
            else:
                logger.warning(f"Final OGG upload failed: {resp.status_code} {resp.text[:200]}")

        except subprocess.TimeoutExpired:
            logger.warning("Final OGG conversion timed out")
        except Exception as e:
            logger.warning(f"Final OGG upload failed: {e}")
        finally:
            if ogg_path:
                try:
                    os.unlink(ogg_path)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_slide_id(self, slide_number: int) -> Optional[str]:
        if not self._slide_id_resolver or slide_number <= 0:
            return None
        try:
            return self._slide_id_resolver(slide_number)
        except Exception:
            return None

    def _start_worker(self):
        if self._worker and self._worker.is_alive():
            return
        self._worker_stop.clear()
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="voice-upload-worker"
        )
        self._worker.start()

    def _stop_worker(self):
        self._worker_stop.set()
        # Sentinel unblocks the worker's queue.get
        self._queue.put(None)

    def _worker_loop(self):
        """Single consumer: uploads chunks strictly in enqueue order."""
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    if self._worker_stop.is_set():
                        return
                    continue  # spurious sentinel from an earlier stop
                index, pcm_data, slide_number, timestamp_seconds = item
                self._upload_chunk_sync(index, pcm_data, slide_number, timestamp_seconds)
            except Exception as e:
                logger.error(f"Voice upload worker error: {e}", exc_info=True)
            finally:
                self._queue.task_done()

    def _upload_chunk_sync(self, index: int, pcm_data: bytes, slide_number: int, timestamp_seconds: float):
        """Convert to Opus (if available) and upload with retry."""
        recording_id = self._recording_id
        if not recording_id:
            return

        # Convert PCM → OGG/Opus at the recorder's actual rate (NOT 44100
        # by default — the device might run at 48000 or 16000).
        if self._use_opus:
            upload_data = _pcm_to_opus(
                pcm_data,
                sample_rate=self._sample_rate,
                channels=self._channels,
            )
            if upload_data is None:
                # Fallback to raw PCM
                upload_data = pcm_data
                content_type = "application/octet-stream"
                ext = "raw"
            else:
                content_type = "audio/ogg"
                ext = "ogg"
        else:
            upload_data = pcm_data
            content_type = "application/octet-stream"
            ext = "raw"

        # Upload with retry
        success = False
        for attempt in range(3):
            try:
                files = {
                    "file": (
                        f"chunk_{index:04d}.{ext}",
                        io.BytesIO(upload_data),
                        content_type,
                    ),
                }
                resp = requests.post(
                    f"{self._api_url}/api/voice/upload-chunk/{recording_id}",
                    files=files,
                    params={"chunk_index": index},
                    headers=self._headers,
                    timeout=60,
                )
                if resp.status_code == 200:
                    total = resp.json().get("total_size", 0)
                    logger.debug(
                        f"Voice chunk #{index} uploaded: "
                        f"{len(pcm_data)} PCM → {len(upload_data)} {ext} "
                        f"(total on server: {total})"
                    )
                    success = True
                    break
                else:
                    logger.warning(f"Voice chunk upload failed: {resp.status_code}")
            except Exception as e:
                logger.warning(f"Voice chunk upload attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(5)

        if not success:
            logger.error(
                f"Voice chunk #{index} upload failed after 3 retries "
                f"({len(upload_data)} bytes lost)"
            )

        # Add slide marker (best-effort; the bulk sync_markers at talk end
        # reconciles any losses here)
        if slide_number > 0:
            try:
                params = {
                    "slide_number": slide_number,
                    "timestamp_seconds": timestamp_seconds,
                }
                slide_id = self._resolve_slide_id(slide_number)
                if slide_id:
                    params["slide_id"] = slide_id
                resp = requests.post(
                    f"{self._api_url}/api/voice/desktop/marker/{recording_id}",
                    params=params,
                    headers=self._headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.debug(f"Voice marker uploaded: slide {slide_number} @ {timestamp_seconds:.1f}s")
            except Exception as e:
                logger.warning(f"Voice marker upload failed: {e}")
