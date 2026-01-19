"""Cloud storage provider for uploading slides to Railway/SeenSlide Cloud."""

import logging
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
        self.session_token: Optional[str] = None
        self.cloud_session_id: Optional[str] = None
        self.enabled = False

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
        self.session_token = config.get("session_token", "")
        self.enabled = config.get("enabled", False)

        if self.enabled:
            if not self.api_url or not self.session_token:
                logger.warning("Cloud sync enabled but missing api_url or session_token")
                self.enabled = False
                return False
            else:
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
                "max_slides": 100
            }

            # Add admin credentials if provided (for device portability)
            if admin_username and admin_password_hash:
                data["admin_username"] = admin_username
                data["admin_password_hash"] = admin_password_hash
                logger.info(f"Registering session with admin credentials: {admin_username}")

            logger.info(f"Creating cloud session: {session_name}")
            response = requests.post(url, headers=headers, json=data, timeout=10)
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
                except:
                    pass
            self.enabled = False  # Disable on error
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
            logger.info(f"✅ Talk created in cloud: {talk_name}")
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

    def save_slide(self, slide: ProcessedSlide, image_data: bytes = None) -> str:
        """Upload slide to cloud.

        Args:
            slide: ProcessedSlide object
            image_data: Image data in bytes (optional, reads from slide.image_path if not provided)

        Returns:
            Slide ID if successful
        """
        if not self.enabled or not self.cloud_session_id:
            return slide.slide_id  # Return slide ID if disabled

        try:
            url = f"{self.api_url}/api/cloud/session/{self.cloud_session_id}/upload-slide?slide_number={slide.sequence_number}"
            headers = {
                "Authorization": f"Bearer {self.session_token}"
            }

            # Prepare image file
            files = {
                "file": (f"slide_{slide.sequence_number:03d}.jpg", image_data, "image/jpeg")
            }

            logger.debug(f"Uploading slide {slide.sequence_number} to cloud...")
            response = requests.post(url, headers=headers, files=files, timeout=30)
            response.raise_for_status()

            logger.info(f"✅ Uploaded slide {slide.sequence_number} to cloud")
            return slide.slide_id

        except Exception as e:
            logger.error(f"Failed to upload slide {slide.sequence_number}: {e}")
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

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists in the cloud.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists, False otherwise
        """
        if not self.enabled:
            return True  # Assume exists if cloud disabled

        try:
            url = f"{self.api_url}/api/cloud/session/{session_id}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                logger.info(f"✅ Session {session_id} exists in cloud")
                return True
            elif response.status_code == 404:
                logger.warning(f"❌ Session {session_id} not found in cloud")
                return False
            else:
                logger.error(f"Failed to check session: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to check session existence: {e}")
            return False

    def cleanup(self):
        """Cleanup cloud storage."""
        logger.info("Cloud storage cleanup")
        self.cloud_session_id = None
