"""Cloud sessions client — list and create sessions for the logged-in user.

Standalone HTTP client that does not depend on the orchestrator or
storage manager. Reads `cloud.api_url` and `cloud.session_token` from
~/.config/seenslide/config.yaml (falling back to the bundled config).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

logger = logging.getLogger(__name__)


CONFIG_PATHS = [
    Path.home() / ".config" / "seenslide" / "config.yaml",
    Path(__file__).parent.parent / "config" / "config.yaml",
]


def _load_cloud_config() -> Dict[str, Any]:
    for path in CONFIG_PATHS:
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = yaml.safe_load(f) or {}
                return data.get("cloud", {}) or {}
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")
    return {}


class CloudSessionsClient:
    """Thin HTTP client for /api/cloud/sessions and /api/cloud/session/create.

    Authentication comes from `DesktopIdentity` (the bearer token bootstrapped
    on first launch), not from config.yaml. The api_url still comes from
    config.yaml so a single value can be overridden in dev.
    """

    def __init__(self, api_url: Optional[str] = None, token: Optional[str] = None):
        cfg = _load_cloud_config()
        self.api_url = (api_url or cfg.get("api_url", "")).rstrip("/")
        self._explicit_token = token  # mostly for tests
        self.timeout = 10

    def _current_token(self) -> str:
        if self._explicit_token:
            return self._explicit_token
        # Lazy import to avoid a circular dep with core.identity (which reads config too).
        from core.identity import identity
        return identity().token or ""

    def is_configured(self) -> bool:
        """True if api_url and a non-placeholder token are set."""
        if not self.api_url:
            return False
        token = self._current_token()
        if not token:
            return False
        if token.lower().startswith("your-"):
            return False
        return True

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._current_token()}",
            "Content-Type": "application/json",
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Fetch all sessions visible to the current user.

        Returns a list of session dicts. Empty list on error.
        """
        if not self.is_configured():
            logger.info("CloudSessionsClient: not configured, skipping list")
            return []

        url = f"{self.api_url}/api/cloud/sessions"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
            sessions = payload.get("sessions", [])
            logger.info(f"Fetched {len(sessions)} sessions from cloud")
            return sessions
        except Exception as e:
            logger.warning(f"Failed to list cloud sessions: {e}")
            return []

    def create_session(
        self,
        title: str,
        presenter_email: str = "",
        max_slides: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """Create a new session. `title` is sent as `presenter_name`.

        Returns the response dict (with `session_id`) on success, None on failure.
        """
        if not self.is_configured():
            logger.warning("CloudSessionsClient: cannot create session, not configured")
            return None

        url = f"{self.api_url}/api/cloud/session/create"
        body: Dict[str, Any] = {
            "presenter_name": title,
            "name": title,  # explicit collection name (server also falls back to presenter_name)
            "max_slides": max_slides,
        }
        if presenter_email:
            body["presenter_email"] = presenter_email

        try:
            resp = requests.post(url, headers=self._headers(), json=body, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Created cloud session: {data.get('session_id')}")
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to create cloud session: {e}")
            if e.response is not None:
                try:
                    logger.error(f"Response body: {e.response.text}")
                except Exception:
                    pass
            return None
        except Exception as e:
            logger.error(f"Failed to create cloud session: {e}")
            return None
