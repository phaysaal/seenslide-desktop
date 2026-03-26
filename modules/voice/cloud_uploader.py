"""Uploads voice audio chunks to the cloud backend after each slide change.

Each PCM chunk is converted to OGG/Opus via ffmpeg before uploading,
reducing bandwidth ~10x (86 KB/s raw → ~8 KB/s Opus). If ffmpeg is
not available, falls back to uploading raw PCM.

Server stores each chunk as a separate .ogg file and concatenates
them into a single file when the recording stops.
"""

import io
import logging
import shutil
import subprocess
import threading
from typing import Optional

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

    def __init__(self, api_url: str, session_token: str = ""):
        self._api_url = api_url.rstrip("/")
        self._session_token = session_token
        self._recording_id: Optional[str] = None
        self._chunk_index: int = 0
        self._use_opus = FFMPEG_AVAILABLE
        self._headers = {
            "Authorization": f"Bearer {self._session_token}" if session_token else "",
        }

        if self._use_opus:
            logger.info("Voice upload: ffmpeg found — will compress to Opus (~10x smaller)")
        else:
            logger.info("Voice upload: ffmpeg not found — uploading raw PCM")

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
            params = {"audio_format": fmt}
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
                self._chunk_index = 0
                logger.info(f"Cloud voice recording started: {self._recording_id} (format: {fmt})")
                return True
            else:
                logger.warning(f"Failed to start cloud voice recording: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Cloud voice start failed: {e}")
            return False

    def upload_chunk(self, pcm_data: bytes, slide_number: int = 0, timestamp_seconds: float = 0.0):
        """Upload an audio chunk (background thread)."""
        if not self._recording_id or not pcm_data:
            return

        t = threading.Thread(
            target=self._upload_chunk_sync,
            args=(pcm_data, slide_number, timestamp_seconds),
            daemon=True,
            name="voice-chunk-upload",
        )
        t.start()

    def upload_chunk_blocking(self, pcm_data: bytes, slide_number: int = 0, timestamp_seconds: float = 0.0):
        """Upload an audio chunk synchronously (for final chunk)."""
        if not self._recording_id or not pcm_data:
            return
        self._upload_chunk_sync(pcm_data, slide_number, timestamp_seconds)

    def stop_cloud_recording(self, duration_seconds: float = 0.0):
        """Finalize the cloud recording."""
        if not self._recording_id:
            return

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
        import subprocess
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

    def _upload_chunk_sync(self, pcm_data: bytes, slide_number: int, timestamp_seconds: float):
        """Convert to Opus (if available) and upload with retry."""
        # Convert PCM → OGG/Opus
        if self._use_opus:
            upload_data = _pcm_to_opus(pcm_data)
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

        self._chunk_index += 1

        # Upload with retry
        success = False
        for attempt in range(3):
            try:
                files = {
                    "file": (
                        f"chunk_{self._chunk_index:04d}.{ext}",
                        io.BytesIO(upload_data),
                        content_type,
                    ),
                }
                resp = requests.post(
                    f"{self._api_url}/api/voice/upload-chunk/{self._recording_id}",
                    files=files,
                    headers=self._headers,
                    timeout=60,
                )
                if resp.status_code == 200:
                    total = resp.json().get("total_size", 0)
                    logger.debug(
                        f"Voice chunk #{self._chunk_index} uploaded: "
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
                import time
                time.sleep(5)

        if not success:
            logger.error(
                f"Voice chunk #{self._chunk_index} upload failed after 3 retries "
                f"({len(upload_data)} bytes lost)"
            )

        # Add slide marker
        if slide_number > 0:
            try:
                resp = requests.post(
                    f"{self._api_url}/api/voice/desktop/marker/{self._recording_id}",
                    params={
                        "slide_number": slide_number,
                        "timestamp_seconds": timestamp_seconds,
                    },
                    headers=self._headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.debug(f"Voice marker uploaded: slide {slide_number} @ {timestamp_seconds:.1f}s")
            except Exception as e:
                logger.warning(f"Voice marker upload failed: {e}")
