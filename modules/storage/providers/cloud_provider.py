"""Cloud storage provider for uploading slides to Railway/SeenSlide Cloud."""

import logging
import threading
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image
import io

from core.interfaces.storage import IStorageProvider
from core.models.slide import ProcessedSlide
from core.models.session import Session

logger = logging.getLogger(__name__)


class CloudStorageProvider(IStorageProvider):
    """Storage provider that uploads slides to cloud (Railway)."""

    def __init__(self):
        """Initialize cloud storage provider."""
        self.api_url: Optional[str] = None
        # Override only set if `initialize()` is called with a literal session_token
        # (legacy path). The live token comes from DesktopIdentity.
        self._session_token_override: Optional[str] = None
        self.cloud_session_id: Optional[str] = None
        self.current_talk_id: Optional[str] = None
        self.enabled = False
        # slide_number → cloud slide_id for the current talk. Filled as
        # slide uploads succeed; consumed by voice markers (stable ids
        # survive slide reordering) — reset whenever a new talk starts.
        self.slide_ids_by_number: dict = {}
        # True between go_live() and end_live() for the current talk.
        self._live = False
        # Newest slide number a navigate was requested for (staleness guard)
        self._navigate_target = 0

    @property
    def session_token(self) -> str:
        """Live bearer token. Pulls from DesktopIdentity unless overridden."""
        if self._session_token_override:
            return self._session_token_override
        try:
            from core.identity import identity
            return identity().token or ""
        except Exception:
            return ""

    @session_token.setter
    def session_token(self, value: Optional[str]) -> None:
        """Allow legacy callers to set a token (treated as override)."""
        self._session_token_override = value or None

    @property
    def name(self) -> str:
        """Provider name."""
        return "cloud"

    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize cloud storage with configuration.

        Args:
            config: Configuration dictionary with:
                - api_url: Cloud API URL
                - session_token: User session token
                - enabled: Whether cloud sync is enabled

        Returns:
            True if initialized successfully
        """
        self.api_url = config.get("api_url", "").rstrip("/")
        # Only set an override if config supplied a real (non-placeholder) token.
        legacy_token = config.get("session_token", "") or ""
        if legacy_token and not legacy_token.lower().startswith("your-"):
            self._session_token_override = legacy_token
        else:
            self._session_token_override = None
        self.enabled = config.get("enabled", False)

        if self.enabled:
            if not self.api_url:
                logger.warning("Cloud sync enabled but api_url missing")
                self.enabled = False
                return False
            if not self.session_token:
                logger.warning(
                    "Cloud sync enabled but no bearer token available "
                    "(DesktopIdentity not bootstrapped yet?)"
                )
                # Don't disable — bootstrap may complete shortly after.
            logger.info(f"Cloud storage initialized: {self.api_url}")
            return True
        else:
            logger.info("Cloud storage disabled")
            return True

    def create_session(self, session: Session) -> str:
        """Create session in cloud.

        Args:
            session: Session object

        Returns:
            Session ID
        """
        return self.start_session(
            session_id=session.session_id,
            session_name=session.name,
            description=session.description,
            presenter_name=session.presenter_name
        )

    def start_session(
        self,
        session_id: str,
        session_name: str,
        description: str = "",
        presenter_name: str = "",
        admin_username: str = None,
        admin_password_hash: str = None
    ) -> str:
        """Create session in cloud.

        Args:
            session_id: Local session ID
            session_name: Session name
            description: Session description
            presenter_name: Presenter name
            admin_username: Admin username for session ownership (optional)
            admin_password_hash: Admin password hash for verification (optional)

        Returns:
            Session ID if successful, empty string if failed
        """
        if not self.enabled:
            return session_id  # Return local ID if cloud disabled

        try:
            url = f"{self.api_url}/api/cloud/session/create"
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            data = {
                "name": session_name,
                "presenter_name": presenter_name or "Unknown",
                "description": description,
                "is_private": False,
                "max_slides": 50
            }

            # Add admin credentials if provided (for device portability)
            if admin_username and admin_password_hash:
                data["admin_username"] = admin_username
                data["admin_password_hash"] = admin_password_hash
                logger.info(f"Registering session with admin credentials: {admin_username}")

            logger.info(f"Creating cloud session: {session_name}")
            # 30s timeout — Railway cold-starts can take >10s and we don't
            # want to permanently brick cloud sync over a single slow request.
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            self.cloud_session_id = result.get("session_id")

            if self.cloud_session_id:
                logger.info(f"✅ Cloud session created: {self.cloud_session_id}")
                logger.info(f"📺 Viewer URL: {self.api_url}/{self.cloud_session_id}")
                return self.cloud_session_id
            else:
                logger.error("Failed to get cloud session ID")
                return ""

        except Exception as e:
            logger.error(f"Failed to create cloud session: {e}", exc_info=True)
            # Print response details if available
            if hasattr(e, 'response'):
                try:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                except Exception:
                    pass
            # Do NOT disable the cloud provider on a single transient
            # failure. The user may select a different (existing) session
            # next, or network may recover. Individual upload calls log
            # their own failures without disabling the provider globally.
            return ""

    def create_talk(
        self,
        session_id: str,
        talk_name: str,
        presenter_name: str = "",
        description: str = ""
    ) -> bool:
        """Create a talk in the cloud session.

        Args:
            session_id: Local session ID
            talk_name: Name of the talk
            presenter_name: Presenter name (ignored by API)
            description: Talk description

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.cloud_session_id:
            logger.debug("Cloud disabled or no cloud session, skipping talk creation")
            return True  # Return success if cloud disabled

        try:
            url = f"{self.api_url}/api/cloud/session/{self.cloud_session_id}/start-talk"
            headers = {
                "Content-Type": "application/json"
            }
            data = {
                "title": talk_name,
                "description": description or ""
            }

            logger.info(f"Creating talk in cloud session {self.cloud_session_id}: {talk_name}")
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()

            result = response.json()
            # Store the talk_id for slide and voice recording association
            talk_data = result.get("talk", {})
            self.current_talk_id = talk_data.get("talk_id")
            if not self.current_talk_id:
                logger.error(f"Failed to get talk_id from API response: {result}")
                return False
            self.slide_ids_by_number = {}
            logger.info(f"✅ Talk created in cloud: {talk_name} (talk_id: {self.current_talk_id})")

            # A talk in the desktop app starts exactly when presenting
            # starts, so go live immediately — viewers polling
            # /live-state begin following this talk's current slide.
            self.go_live()
            return True

        except Exception as e:
            logger.error(f"Failed to create talk in cloud: {e}", exc_info=True)
            if hasattr(e, 'response'):
                try:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                except:
                    pass
            # Don't disable cloud on talk creation failure
            return False

    def end_talk(self, talk_id: Optional[str] = None) -> bool:
        """Tell the cloud that a talk has finished.

        Marks cloud_talks.status='completed' and stamps end_time on the
        server, so viewers stop showing the LIVE badge and the parent
        cloud_sessions row no longer flags this talk as the active one.

        Args:
            talk_id: Cloud talk_id to end. Defaults to current_talk_id.

        Returns:
            True if the talk was acknowledged as ended (or no-op when
            cloud is disabled / nothing to end). False on HTTP failure.
        """
        if not self.enabled or not self.cloud_session_id:
            return True
        tid = talk_id or self.current_talk_id
        if not tid:
            return True  # nothing to end

        # End the live-follow session first so viewers stop polling a
        # talk that's about to be marked completed.
        self.end_live(tid)

        try:
            url = f"{self.api_url}/api/cloud/talk/{tid}/end"
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json",
            }
            response = requests.post(url, headers=headers, timeout=10)
            response.raise_for_status()
            if self.current_talk_id == tid:
                self.current_talk_id = None
            logger.info(f"✅ Ended talk in cloud: {tid}")
            return True
        except Exception as e:
            logger.error(f"Failed to end talk {tid} in cloud: {e}", exc_info=True)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.error(f"Response body: {e.response.text}")
                except Exception:
                    pass
            return False

    # ------------------------------------------------------------------
    # Live slide-follow (viewers poll /api/cloud/talk/{id}/live-state)
    # ------------------------------------------------------------------

    def go_live(self, talk_id: Optional[str] = None) -> bool:
        """Mark the talk live on the server so viewers can follow along.

        Failure is non-fatal — the talk proceeds normally, viewers just
        don't get live slide-follow.
        """
        if not self.enabled:
            return False
        tid = talk_id or self.current_talk_id
        if not tid:
            return False
        try:
            resp = requests.post(
                f"{self.api_url}/api/cloud/talk/{tid}/go-live",
                headers={"Authorization": f"Bearer {self.session_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            self._live = True
            logger.info(f"🔴 Talk live: {tid}")
            return True
        except Exception as e:
            logger.warning(f"go-live failed for talk {tid}: {e}")
            return False

    def navigate_slide(self, slide_number: int, talk_id: Optional[str] = None) -> bool:
        """Push the presenter's current slide number to live viewers.

        Called from short-lived background threads; only the newest
        requested slide is worth delivering. _navigate_target tracks the
        latest request so a thread that was stuck behind a slow request
        (or a retry) drops out instead of delivering a stale slide after
        a newer one already landed.
        """
        if not self.enabled or slide_number < 1:
            return False
        tid = talk_id or self.current_talk_id
        if not tid:
            return False
        self._navigate_target = slide_number
        try:
            resp = requests.post(
                f"{self.api_url}/api/cloud/talk/{tid}/navigate",
                json={"slide_number": slide_number},
                headers={"Authorization": f"Bearer {self.session_token}"},
                timeout=5,
            )
            if resp.status_code == 400 and self._navigate_target == slide_number:
                # Talk isn't live server-side (e.g. server restarted and
                # lost in-memory live state) — re-establish and retry once.
                if self.go_live(tid):
                    resp = requests.post(
                        f"{self.api_url}/api/cloud/talk/{tid}/navigate",
                        json={"slide_number": slide_number},
                        headers={"Authorization": f"Bearer {self.session_token}"},
                        timeout=5,
                    )
            resp.raise_for_status()
            logger.debug(f"Live navigate: slide {slide_number}")
            return True
        except Exception as e:
            if self._navigate_target != slide_number:
                logger.debug(f"Live navigate superseded (slide {slide_number})")
            else:
                logger.warning(f"Live navigate failed (slide {slide_number}): {e}")
            return False

    def end_live(self, talk_id: Optional[str] = None) -> bool:
        """End the live-follow session for the talk."""
        if not self.enabled:
            return False
        tid = talk_id or self.current_talk_id
        if not tid:
            self._live = False
            return False
        try:
            resp = requests.post(
                f"{self.api_url}/api/cloud/talk/{tid}/end-live",
                headers={"Authorization": f"Bearer {self.session_token}"},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info(f"⬛ Talk live ended: {tid}")
            return True
        except Exception as e:
            logger.warning(f"end-live failed for talk {tid}: {e}")
            return False
        finally:
            self._live = False

    def save_slide(self, slide: ProcessedSlide, image_data: bytes = None) -> str:
        """Upload slide to cloud.

        Args:
            slide: ProcessedSlide object
            image_data: Image data in bytes (optional, reads from slide.image_path if not provided)

        Returns:
            Slide ID if successful
        """
        if not self.enabled:
            return slide.slide_id

        # Prefer talk_id from slide, fallback to current_talk_id
        talk_id = slide.talk_id or self.current_talk_id

        if not talk_id:
            logger.warning(f"No talk_id for slide {slide.sequence_number}, skipping cloud upload")
            return slide.slide_id

        try:
            # Use talk-specific endpoint for correct hierarchy (verified to work)
            url = f"{self.api_url}/api/cloud/talk/{talk_id}/upload-slide?slide_number={slide.sequence_number}"
            headers = {
                "Authorization": f"Bearer {self.session_token}"
            }

            # Prepare image file
            files = {
                "file": (f"slide_{slide.sequence_number:03d}.jpg", image_data, "image/jpeg")
            }

            logger.debug(f"Uploading slide {slide.sequence_number} to talk {talk_id}...")
            response = requests.post(url, headers=headers, files=files, timeout=30)
            response.raise_for_status()

            # Remember the cloud's stable slide_id for this slide number —
            # voice markers prefer it over the reorder-fragile slide_number.
            try:
                body = response.json()
                cloud_slide_id = (
                    body.get("slide_id")
                    or body.get("slide", {}).get("slide_id")
                )
                if cloud_slide_id:
                    self.slide_ids_by_number[slide.sequence_number] = cloud_slide_id
            except Exception:
                pass

            logger.info(f"✅ Uploaded slide {slide.sequence_number} to talk {talk_id}")

            # Tell live viewers the presenter is now on this slide. The
            # newest unique slide IS the current slide during a talk.
            # Fire-and-forget: this runs on the slide-storage thread, and a
            # slow server (observed 10s+ read timeouts under load) must not
            # stall the capture→store pipeline for a best-effort UI ping.
            if self._live:
                threading.Thread(
                    target=self.navigate_slide,
                    args=(slide.sequence_number, talk_id),
                    daemon=True,
                    name="live-navigate",
                ).start()

            return slide.slide_id

        except Exception as e:
            logger.error(f"Failed to upload slide {slide.sequence_number}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.error(f"Response body: {e.response.text}")
                except Exception:
                    pass
            # Don't disable on single slide failure
            return slide.slide_id

    def get_slide(self, slide_id: str) -> Optional[ProcessedSlide]:
        """Get slide from cloud (not implemented - use local storage)."""
        return None

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session from cloud (not implemented - use local storage)."""
        return None

    def update_session(self, session: Session) -> bool:
        """Update session in cloud (not implemented)."""
        return True

    def list_slides(self, session_id: str, limit: Optional[int] = None, offset: int = 0) -> list:
        """List slides from cloud (not implemented - use local storage)."""
        return []

    def get_slide_count(self, session_id: str) -> int:
        """Get slide count (not implemented - use local storage)."""
        return 0

    def delete_slide(self, session_id: str, slide_id: str) -> bool:
        """Delete slide from cloud.

        Args:
            session_id: Session ID
            slide_id: Slide ID

        Returns:
            True if successful
        """
        if not self.enabled or not self.cloud_session_id:
            return True

        try:
            url = f"{self.api_url}/api/cloud/session/{self.cloud_session_id}/slide/{slide_id}"
            headers = {
                "Authorization": f"Bearer {self.session_token}"
            }

            response = requests.delete(url, headers=headers, timeout=10)
            response.raise_for_status()

            logger.info(f"Deleted slide {slide_id} from cloud")
            return True

        except Exception as e:
            logger.error(f"Failed to delete slide from cloud: {e}")
            return False

    def delete_slide_by_number(self, talk_id: str, slide_number: int) -> bool:
        """Delete a slide from the cloud by (talk_id, slide_number).

        The cloud assigns its OWN slide_id on upload, so the local
        slide.slide_id does not match the cloud row — delete-by-id silently
        fails. talk_id + slide_number is the reliable key the desktop holds.
        Server-side this also cascades the slide's voice-sync markers, so
        surviving slides stay in sync.
        """
        if not self.enabled:
            return True
        if not talk_id:
            return False

        try:
            url = f"{self.api_url}/api/cloud/talk/{talk_id}/slide/{slide_number}"
            headers = {"Authorization": f"Bearer {self.session_token}"}
            response = requests.delete(url, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Deleted slide #{slide_number} (talk {talk_id}) from cloud")
            return True
        except Exception as e:
            logger.error(f"Failed to delete slide #{slide_number} from cloud: {e}")
            return False

    def session_exists(self, session_id: str) -> bool:
        """Check if a cloud session exists by doing a GET request.

        Args:
            session_id: Session ID to check

        Returns:
            True only if the cloud reports the session exists. Returns
            False when cloud is disabled or unreachable — callers should
            treat that as "we can't confirm, so assume no."
        """
        if not self.enabled:
            return False

        try:
            url = f"{self.api_url}/api/cloud/session/{session_id}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Session {session_id} exists in cloud")
                return True
            if response.status_code == 404:
                logger.warning(f"❌ Session {session_id} not found in cloud")
                return False
            logger.error(
                f"Unexpected status checking session {session_id}: "
                f"{response.status_code}"
            )
            return False
        except Exception as e:
            logger.warning(f"Failed to check if session exists: {e}")
            return False

    def verify_session(
        self,
        session_id: str,
        admin_username: str,
        admin_password_hash: str
    ) -> bool:
        """Verify session ID with admin credentials (for cross-device access).

        Args:
            session_id: Session ID to verify
            admin_username: Admin username
            admin_password_hash: Admin password hash

        Returns:
            True if session ID + credentials match in cloud, False otherwise
        """
        if not self.enabled:
            logger.warning("Cloud disabled, cannot verify session")
            return False

        try:
            url = f"{self.api_url}/api/cloud/session/verify"
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json"
            }
            data = {
                "session_id": session_id,
                "admin_username": admin_username,
                "admin_password_hash": admin_password_hash
            }

            logger.info(f"Verifying session {session_id} with credentials...")
            response = requests.post(url, headers=headers, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                verified = result.get("verified", False)
                if verified:
                    logger.info(f"✅ Session {session_id} verified successfully")
                    self.cloud_session_id = session_id
                    return True
                else:
                    logger.warning(f"❌ Session verification failed: Invalid credentials")
                    return False
            else:
                logger.error(f"Session verification failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to verify session: {e}")
            return False

    def update_collection_alias(
        self,
        collection_id: str,
        alias: Optional[str]
    ) -> bool:
        """Update collection alias.

        Args:
            collection_id: Cloud collection ID
            alias: New alias (None to remove)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.warning("Cloud disabled, cannot update alias")
            return False

        try:
            url = f"{self.api_url}/api/cloud/session/{collection_id}/alias"
            headers = {
                "Content-Type": "application/json"
            }
            data = {
                "alias": alias
            }

            logger.info(f"Updating alias for collection {collection_id}: {alias}")
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()

            logger.info(f"✅ Alias updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to update alias: {e}", exc_info=True)
            if hasattr(e, 'response'):
                try:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                except:
                    pass
            return False

    def update_collection_password(
        self,
        collection_id: str,
        admin_username: str,
        new_password_hash: str
    ) -> bool:
        """Update collection password.

        Args:
            collection_id: Cloud collection ID
            admin_username: Admin username
            new_password_hash: New bcrypt password hash

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.warning("Cloud disabled, cannot update password")
            return False

        try:
            url = f"{self.api_url}/api/cloud/session/{collection_id}/password"
            headers = {
                "Content-Type": "application/json"
            }
            data = {
                "admin_username": admin_username,
                "new_password_hash": new_password_hash
            }

            logger.info(f"Updating password for collection {collection_id}")
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()

            logger.info(f"✅ Password updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to update password: {e}", exc_info=True)
            if hasattr(e, 'response'):
                try:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                except:
                    pass
            return False

    def get_collection_info(
        self,
        collection_id_or_alias: str
    ) -> Optional[Dict[str, Any]]:
        """Get collection information.

        Args:
            collection_id_or_alias: Cloud collection ID or alias

        Returns:
            Collection info dict or None
        """
        if not self.enabled:
            logger.warning("Cloud disabled, cannot get collection info")
            return None

        try:
            url = f"{self.api_url}/api/cloud/session/{collection_id_or_alias}"
            headers = {
                "Content-Type": "application/json"
            }

            logger.info(f"Getting collection info: {collection_id_or_alias}")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            result = response.json()
            logger.info(f"✅ Collection info retrieved")
            return result

        except Exception as e:
            logger.error(f"Failed to get collection info: {e}", exc_info=True)
            if hasattr(e, 'response'):
                try:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                except:
                    pass
            return None

    def verify_collection_password(
        self,
        collection_id_or_alias: str,
        password: str
    ) -> Optional[Dict[str, Any]]:
        """Verify collection password and get access.

        Args:
            collection_id_or_alias: Cloud collection ID or alias
            password: Plain text password to verify

        Returns:
            Dict with collection_id, owner_username, and session_token if successful, None otherwise
        """
        if not self.enabled:
            logger.warning("Cloud disabled, cannot verify password")
            return None

        try:
            url = f"{self.api_url}/api/cloud/session/{collection_id_or_alias}/verify"
            headers = {
                "Content-Type": "application/json"
            }
            data = {
                "password": password
            }

            logger.info(f"Verifying password for collection: {collection_id_or_alias}")
            response = requests.post(url, headers=headers, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get("verified"):
                    logger.info(f"✅ Collection password verified")
                    return {
                        "collection_id": result.get("session_id"),
                        "owner_username": result.get("owner_username"),
                        "session_token": result.get("session_token"),
                        "name": result.get("name")
                    }
                else:
                    logger.warning(f"❌ Password verification failed")
                    return None
            else:
                logger.error(f"Password verification failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Failed to verify password: {e}", exc_info=True)
            if hasattr(e, 'response'):
                try:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                except:
                    pass
            return None

    def cleanup(self):
        """Cleanup cloud storage."""
        logger.info("Cloud storage cleanup")
        self.cloud_session_id = None
