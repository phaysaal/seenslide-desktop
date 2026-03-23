"""Uploads voice audio chunks to the cloud backend after each slide change.

Lifecycle (driven by the orchestrator):
    uploader = VoiceCloudUploader(api_url, session_token, cloud_session_id)
    uploader.start_cloud_recording(cloud_session_id)   # POST /desktop/start
    ...
    uploader.upload_chunk(pcm_bytes, slide_number, ts)  # POST /upload-chunk + /desktop/marker
    ...
    uploader.stop_cloud_recording(duration)             # POST /desktop/stop
"""

import io
import logging
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class VoiceCloudUploader:
    """Uploads voice chunks + markers to the SeenSlide cloud backend."""

    def __init__(self, api_url: str, session_token: str = ""):
        self._api_url = api_url.rstrip("/")
        self._session_token = session_token
        self._recording_id: Optional[str] = None
        self._headers = {
            "Authorization": f"Bearer {self._session_token}" if session_token else "",
        }

    @property
    def recording_id(self) -> Optional[str]:
        return self._recording_id

    # ------------------------------------------------------------------
    # Cloud recording lifecycle
    # ------------------------------------------------------------------

    def start_cloud_recording(self, cloud_session_id: str, audio_format: str = "wav") -> bool:
        """Tell the cloud to create a new voice recording entry.

        Returns True if successful (sets self._recording_id).
        """
        try:
            resp = requests.post(
                f"{self._api_url}/api/voice/desktop/start/{cloud_session_id}",
                params={"audio_format": audio_format},
                headers=self._headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._recording_id = data.get("recording_id")
                logger.info(f"Cloud voice recording started: {self._recording_id}")
                return True
            else:
                logger.warning(f"Failed to start cloud voice recording: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Cloud voice start failed: {e}")
            return False

    def upload_chunk(self, pcm_data: bytes, slide_number: int = 0, timestamp_seconds: float = 0.0):
        """Upload an audio chunk and optionally add a slide marker.

        Called in a background thread so it doesn't block recording.

        Args:
            pcm_data: Raw PCM audio bytes to append.
            slide_number: Current slide number (0 = skip marker).
            timestamp_seconds: Audio timestamp for the marker.
        """
        if not self._recording_id or not pcm_data:
            return

        # Run in background thread to avoid blocking
        t = threading.Thread(
            target=self._upload_chunk_sync,
            args=(pcm_data, slide_number, timestamp_seconds),
            daemon=True,
            name="voice-chunk-upload",
        )
        t.start()

    def stop_cloud_recording(self, duration_seconds: float = 0.0):
        """Finalize the cloud recording."""
        if not self._recording_id:
            return

        try:
            resp = requests.post(
                f"{self._api_url}/api/voice/desktop/stop/{self._recording_id}",
                params={"duration_seconds": duration_seconds},
                headers=self._headers,
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Cloud voice recording stopped: {self._recording_id}")
            else:
                logger.warning(f"Failed to stop cloud voice: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Cloud voice stop failed: {e}")
        finally:
            self._recording_id = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _upload_chunk_sync(self, pcm_data: bytes, slide_number: int, timestamp_seconds: float):
        """Synchronous chunk upload with retry (runs in background thread)."""
        # Upload audio chunk with retry
        success = False
        for attempt in range(3):
            try:
                files = {
                    "file": ("chunk.raw", io.BytesIO(pcm_data), "application/octet-stream"),
                }
                resp = requests.post(
                    f"{self._api_url}/api/voice/upload-chunk/{self._recording_id}",
                    files=files,
                    headers=self._headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    total = resp.json().get("total_size", 0)
                    logger.debug(f"Voice chunk uploaded: +{len(pcm_data)} bytes (total {total})")
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
            logger.error(f"Voice chunk upload failed after 3 retries ({len(pcm_data)} bytes lost)")

        # Add slide marker (no retry needed — markers are idempotent)
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
