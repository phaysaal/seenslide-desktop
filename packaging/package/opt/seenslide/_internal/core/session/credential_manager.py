"""Credential manager for secure password and token storage."""

import logging
from typing import Optional
from pathlib import Path
import json
import hashlib
import platform

logger = logging.getLogger(__name__)


def get_device_fingerprint() -> str:
    """Generate a device fingerprint for session binding.

    Returns:
        Device fingerprint (16-char hex string)
    """
    components = [
        platform.node(),  # hostname
        platform.machine(),  # architecture
        platform.system(),  # OS
    ]
    fingerprint = hashlib.sha256(
        ''.join(components).encode()
    ).hexdigest()[:16]
    return fingerprint


class CredentialManager:
    """Manages secure credential storage using system keyring.

    Falls back to encrypted file storage if keyring is unavailable.
    """

    SERVICE_NAME = "seenslide"

    def __init__(self, use_keyring: bool = True):
        """Initialize credential manager.

        Args:
            use_keyring: Whether to use system keyring (default: True)
        """
        self.keyring_available = False
        self.keyring = None

        if use_keyring:
            try:
                import keyring
                self.keyring = keyring
                self.keyring_available = True
                logger.info("Keyring available, using secure credential storage")
            except ImportError:
                logger.warning("Keyring not available, using fallback storage")
                self._init_fallback_storage()
        else:
            logger.info("Keyring disabled, using fallback storage")
            self._init_fallback_storage()

    def _init_fallback_storage(self):
        """Initialize fallback credential storage (encrypted file)."""
        # Create storage directory
        config_dir = Path.home() / ".config" / "seenslide"
        config_dir.mkdir(parents=True, exist_ok=True)

        self.credentials_file = config_dir / ".credentials.json"

        # Load existing credentials
        if self.credentials_file.exists():
            try:
                with open(self.credentials_file, 'r') as f:
                    self.credentials = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load credentials: {e}")
                self.credentials = {}
        else:
            self.credentials = {}

    def _save_fallback_credentials(self):
        """Save credentials to fallback file."""
        try:
            with open(self.credentials_file, 'w') as f:
                json.dump(self.credentials, f, indent=2)
            # Set restrictive permissions (owner read/write only)
            self.credentials_file.chmod(0o600)
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")

    def store_password_hash(self, collection_id: str, password_hash: str) -> bool:
        """Store password hash for a collection.

        Used when user creates a collection on this device.

        Args:
            collection_id: Cloud collection ID
            password_hash: Bcrypt password hash

        Returns:
            True if successful
        """
        key = f"collection:{collection_id}:password_hash"

        if self.keyring_available:
            try:
                self.keyring.set_password(self.SERVICE_NAME, key, password_hash)
                logger.debug(f"Stored password hash for {collection_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to store password hash: {e}")
                return False
        else:
            self.credentials[key] = password_hash
            self._save_fallback_credentials()
            logger.debug(f"Stored password hash for {collection_id} (fallback)")
            return True

    def get_password_hash(self, collection_id: str) -> Optional[str]:
        """Get stored password hash for a collection.

        Args:
            collection_id: Cloud collection ID

        Returns:
            Password hash or None
        """
        key = f"collection:{collection_id}:password_hash"

        if self.keyring_available:
            try:
                return self.keyring.get_password(self.SERVICE_NAME, key)
            except Exception as e:
                logger.error(f"Failed to get password hash: {e}")
                return None
        else:
            return self.credentials.get(key)

    def store_session_token(self, collection_id: str, session_token: str) -> bool:
        """Store session token for authenticated access.

        Args:
            collection_id: Cloud collection ID
            session_token: JWT session token from cloud

        Returns:
            True if successful
        """
        key = f"collection:{collection_id}:session_token"

        if self.keyring_available:
            try:
                self.keyring.set_password(self.SERVICE_NAME, key, session_token)
                logger.debug(f"Stored session token for {collection_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to store session token: {e}")
                return False
        else:
            self.credentials[key] = session_token
            self._save_fallback_credentials()
            logger.debug(f"Stored session token for {collection_id} (fallback)")
            return True

    def get_session_token(self, collection_id: str) -> Optional[str]:
        """Get stored session token for a collection.

        Args:
            collection_id: Cloud collection ID

        Returns:
            Session token or None
        """
        key = f"collection:{collection_id}:session_token"

        if self.keyring_available:
            try:
                return self.keyring.get_password(self.SERVICE_NAME, key)
            except Exception as e:
                logger.error(f"Failed to get session token: {e}")
                return None
        else:
            return self.credentials.get(key)

    def delete_credentials(self, collection_id: str) -> bool:
        """Delete all credentials for a collection.

        Args:
            collection_id: Cloud collection ID

        Returns:
            True if successful
        """
        keys = [
            f"collection:{collection_id}:password_hash",
            f"collection:{collection_id}:session_token"
        ]

        success = True

        if self.keyring_available:
            for key in keys:
                try:
                    self.keyring.delete_password(self.SERVICE_NAME, key)
                except Exception as e:
                    logger.debug(f"Failed to delete credential {key}: {e}")
                    # Not a critical error - key might not exist
        else:
            for key in keys:
                self.credentials.pop(key, None)
            self._save_fallback_credentials()

        logger.info(f"Deleted credentials for {collection_id}")
        return success

    def has_credentials(self, collection_id: str) -> bool:
        """Check if credentials exist for a collection.

        Args:
            collection_id: Cloud collection ID

        Returns:
            True if either password hash or session token exists
        """
        return (
            self.get_password_hash(collection_id) is not None or
            self.get_session_token(collection_id) is not None
        )
