"""Persistent session manager for maintaining session across talks."""

import logging
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import secrets
import string

logger = logging.getLogger(__name__)


class PersistentSessionManager:
    """Manages persistent session that survives across multiple talks."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize persistent session manager.

        Args:
            config_dir: Configuration directory (defaults to ~/.config/seenslide)
        """
        if config_dir is None:
            config_dir = Path.home() / ".config" / "seenslide"

        self.config_dir = Path(config_dir)
        self.session_file = self.config_dir / "persistent_session.yaml"
        self._session_data: Optional[Dict[str, Any]] = None

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_or_create_session(self, default_name: str = "SeenSlide Session") -> Dict[str, Any]:
        """Load existing persistent session or create a new one.

        Args:
            default_name: Default session name if creating new

        Returns:
            Session data dictionary
        """
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    self._session_data = yaml.safe_load(f)
                    logger.info(f"Loaded persistent session: {self._session_data['session_id']}")
                    return self._session_data
            except Exception as e:
                logger.error(f"Failed to load persistent session: {e}")
                # Fall through to create new session

        # Create new session
        self._session_data = self._create_new_session(default_name)
        self._save_session()
        logger.info(f"Created new persistent session: {self._session_data['session_id']}")
        return self._session_data

    def reset_session(self, new_name: Optional[str] = None) -> Dict[str, Any]:
        """Reset session with new ID.

        Args:
            new_name: Optional new session name

        Returns:
            New session data dictionary
        """
        old_id = self._session_data.get('session_id') if self._session_data else None

        session_name = new_name if new_name else (
            self._session_data.get('session_name', 'SeenSlide Session')
            if self._session_data else 'SeenSlide Session'
        )

        self._session_data = self._create_new_session(session_name)
        self._session_data['last_reset'] = datetime.now().isoformat()
        self._save_session()

        logger.info(f"Reset session from {old_id} to {self._session_data['session_id']}")
        return self._session_data

    def update_cloud_session_id(self, cloud_session_id: str) -> None:
        """Update cloud session ID.

        Args:
            cloud_session_id: Cloud session ID from Railway
        """
        if self._session_data is None:
            logger.warning("No persistent session loaded")
            return

        self._session_data['cloud_session_id'] = cloud_session_id
        self._session_data['cloud_session_created_at'] = datetime.now().isoformat()
        self._save_session()
        logger.info(f"Updated cloud session ID: {cloud_session_id}")

    def get_session_data(self) -> Optional[Dict[str, Any]]:
        """Get current session data.

        Returns:
            Session data dictionary or None
        """
        return self._session_data

    def get_session_id(self) -> Optional[str]:
        """Get current session ID.

        Returns:
            Session ID or None
        """
        return self._session_data.get('session_id') if self._session_data else None

    def get_cloud_session_id(self) -> Optional[str]:
        """Get current cloud session ID.

        Returns:
            Cloud session ID or None
        """
        return self._session_data.get('cloud_session_id') if self._session_data else None

    def update_session_name(self, name: str) -> None:
        """Update session name.

        Args:
            name: New session name
        """
        if self._session_data is None:
            logger.warning("No persistent session loaded")
            return

        self._session_data['session_name'] = name
        self._save_session()
        logger.info(f"Updated session name: {name}")

    def _create_new_session(self, name: str) -> Dict[str, Any]:
        """Create new session data.

        Args:
            name: Session name

        Returns:
            Session data dictionary
        """
        # Generate session ID (format: SESS-ABC-123)
        session_id = self._generate_session_id()

        return {
            'session_id': session_id,
            'session_name': name,
            'created_at': datetime.now().isoformat(),
            'last_reset': datetime.now().isoformat(),
            'cloud_session_id': None,
            'cloud_session_created_at': None,
        }

    def _generate_session_id(self) -> str:
        """Generate a unique session ID.

        Returns:
            Session ID in format SESS-ABC-123
        """
        # Generate 3 random uppercase letters
        letters = ''.join(secrets.choice(string.ascii_uppercase) for _ in range(3))
        # Generate 3 random digits
        digits = ''.join(secrets.choice(string.digits) for _ in range(3))
        return f"SESS-{letters}-{digits}"

    def _save_session(self) -> None:
        """Save session data to file."""
        try:
            with open(self.session_file, 'w') as f:
                yaml.dump(self._session_data, f, default_flow_style=False)
            logger.debug(f"Saved persistent session to {self.session_file}")
        except Exception as e:
            logger.error(f"Failed to save persistent session: {e}")
