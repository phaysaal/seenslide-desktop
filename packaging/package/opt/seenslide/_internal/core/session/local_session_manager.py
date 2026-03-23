"""Local session manager for persistent session ID storage."""

import logging
import yaml
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LocalSessionManager:
    """Manages local session ID persistence across app restarts."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize local session manager.

        Args:
            config_dir: Configuration directory (defaults to ~/.config/seenslide)
        """
        if config_dir is None:
            config_dir = Path.home() / ".config" / "seenslide"

        self.config_dir = Path(config_dir)
        # Store session file directly in config directory
        self.session_file = self.config_dir / "local_session.yaml"

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_session_id(self) -> Optional[str]:
        """Load session ID from local storage.

        Returns:
            Session ID if found, None otherwise
        """
        if not self.session_file.exists():
            return None

        try:
            with open(self.session_file, 'r') as f:
                data = yaml.safe_load(f)
                session_id = data.get('session_id')
                if session_id:
                    logger.info(f"Loaded local session ID: {session_id}")
                    return session_id
                else:
                    logger.warning("Session file exists but no session_id found")
                    return None
        except Exception as e:
            logger.error(f"Failed to load session ID: {e}")
            return None

    def save_session_id(self, session_id: str) -> bool:
        """Save session ID to local storage.

        Args:
            session_id: Session ID to save

        Returns:
            True if saved successfully
        """
        try:
            data = {
                'session_id': session_id
            }
            with open(self.session_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
            logger.info(f"Saved session ID locally: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save session ID: {e}")
            return False

    def clear_session(self) -> bool:
        """Clear local session ID.

        Returns:
            True if cleared successfully
        """
        try:
            if self.session_file.exists():
                self.session_file.unlink()
                logger.info("Cleared local session ID")
            return True
        except Exception as e:
            logger.error(f"Failed to clear session ID: {e}")
            return False
