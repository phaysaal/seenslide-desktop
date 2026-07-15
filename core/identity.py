"""Desktop identity: device id, bearer token, and the auth API client.

A single source of truth for "who is this app talking to the cloud as".

Resolution order for the bearer token:
  1. Token cached locally (CredentialManager) — used as-is on every launch.
  2. If no token, POST /api/auth/device-bootstrap with our device_id;
     server returns a bearer token + (anonymous) user record. Cached.
  3. claim() / login() / logout() rotate the cached token.

The device_id is stable across launches:
  * Linux:   /etc/machine-id  (preferred, OS-provided, stable across reboots)
  * macOS:   IOPlatformUUID via `ioreg`
  * Windows: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
  * Fallback: a locally-generated UUID at ~/.config/seenslide/.device_id

Once any device_id is established for this app install, it is written to
the fallback file so that subsequent launches keep using exactly the same
id even if the OS-provided source changes (which can happen on macOS
reinstall or after `systemd-machine-id-setup --commit` reruns).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import subprocess
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml

from core.session.credential_manager import CredentialManager

logger = logging.getLogger(__name__)


CONFIG_DIR = Path.home() / ".config" / "seenslide"
DEVICE_ID_FILE = CONFIG_DIR / ".device_id"
IDENTITY_CACHE_FILE = CONFIG_DIR / ".identity.json"

CONFIG_PATHS = [
    CONFIG_DIR / "config.yaml",
    Path(__file__).parent.parent / "config" / "config.yaml",
]

CRED_KEY_TOKEN = "auth:bearer_token"
CRED_KEY_USER_ID = "auth:user_id"


# ── Device ID ──────────────────────────────────────────────────────

def _read_linux_machine_id() -> Optional[str]:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(path).read_text().strip()
            if value:
                return value
        except Exception:
            continue
    return None


def _read_macos_platform_uuid() -> Optional[str]:
    try:
        out = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=2,
        )
        for line in out.stdout.splitlines():
            if "IOPlatformUUID" in line:
                # Line shape: "IOPlatformUUID" = "XXXX-XXXX-..."
                return line.split('"')[-2]
    except Exception:
        pass
    return None


def _read_windows_machine_guid() -> Optional[str]:
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return None


def _read_local_device_file() -> Optional[str]:
    try:
        if DEVICE_ID_FILE.exists():
            value = DEVICE_ID_FILE.read_text().strip()
            return value or None
    except Exception:
        return None
    return None


def _write_private(path, text: str) -> None:
    """Write a file that is 0o600 from the moment it exists.

    write_text() + chmod() leaves a window where the file carries the umask
    default (usually world-readable) — os.open with an explicit mode doesn't.
    """
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _persist_device_id(value: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _write_private(DEVICE_ID_FILE, value)
    except Exception as e:
        logger.warning(f"Could not persist device id: {e}")


def get_or_create_device_id() -> str:
    """Resolve a stable device id. Pins it to the local file on first call."""
    cached = _read_local_device_file()
    if cached:
        return cached

    system = platform.system()
    candidate: Optional[str] = None
    if system == "Linux":
        candidate = _read_linux_machine_id()
    elif system == "Darwin":
        candidate = _read_macos_platform_uuid()
    elif system == "Windows":
        candidate = _read_windows_machine_guid()

    if not candidate:
        candidate = str(uuid.uuid4())

    _persist_device_id(candidate)
    return candidate


def get_device_label() -> str:
    """A human-friendly label for the device (used as device_label in API)."""
    try:
        return f"{socket.gethostname()} ({platform.system()})"
    except Exception:
        return platform.system() or "Unknown"


# ── Cached identity record ─────────────────────────────────────────

@dataclass
class IdentityRecord:
    user_id: str = ""
    email: Optional[str] = None
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    is_anonymous: bool = True
    account_tier: str = "free"

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "IdentityRecord":
        return cls(
            user_id=payload.get("user_id", ""),
            email=payload.get("email"),
            phone_number=payload.get("phone_number"),
            full_name=payload.get("full_name"),
            is_anonymous=bool(payload.get("is_anonymous", True)),
            account_tier=payload.get("account_tier") or "free",
        )


def _load_identity_cache() -> IdentityRecord:
    try:
        if IDENTITY_CACHE_FILE.exists():
            data = json.loads(IDENTITY_CACHE_FILE.read_text())
            return IdentityRecord(**{
                k: data.get(k) for k in (
                    "user_id", "email", "phone_number", "full_name",
                    "is_anonymous", "account_tier",
                )
            })
    except Exception as e:
        logger.debug(f"identity cache unreadable: {e}")
    return IdentityRecord()


def _save_identity_cache(record: IdentityRecord) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _write_private(IDENTITY_CACHE_FILE, json.dumps(asdict(record), indent=2))
    except Exception as e:
        logger.warning(f"Could not save identity cache: {e}")


# ── API URL ────────────────────────────────────────────────────────

def _resolve_api_url() -> str:
    for path in CONFIG_PATHS:
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text()) or {}
                url = (data.get("cloud", {}) or {}).get("api_url", "")
                if url:
                    url = url.rstrip("/")
                    # Enforce TLS: a config typo of http:// would silently
                    # send the bearer token, slides, and audio in cleartext.
                    # Plain http is allowed only toward the local machine
                    # (development against a local server).
                    if url.startswith("http://") and not any(
                        h in url for h in ("://localhost", "://127.0.0.1", "://[::1]")
                    ):
                        logger.warning(
                            f"Ignoring non-https api_url from config ({url}) — "
                            f"falling back to https://seenslide.com"
                        )
                        continue
                    return url
            except Exception:
                continue
    return "https://seenslide.com"


# ── DesktopIdentity ────────────────────────────────────────────────

class IdentityError(Exception):
    """Raised when an identity operation fails. status mirrors the API."""
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class DesktopIdentity:
    """Singleton-style identity holder for the running desktop app.

    Use the module-level `identity()` accessor; do not instantiate twice.
    """

    def __init__(self) -> None:
        self.api_url = _resolve_api_url()
        self.cred = CredentialManager()
        self.device_id = get_or_create_device_id()
        self.device_label = get_device_label()
        self._token: Optional[str] = self.cred.get_credential(CRED_KEY_TOKEN)
        cached_user_id = self.cred.get_credential(CRED_KEY_USER_ID)
        self._record = _load_identity_cache()
        if cached_user_id and not self._record.user_id:
            self._record.user_id = cached_user_id

    # ── State ──────────────────────────────────────────────────────

    @property
    def token(self) -> Optional[str]:
        return self._token

    @property
    def record(self) -> IdentityRecord:
        return self._record

    @property
    def is_authenticated(self) -> bool:
        return bool(self._token)

    @property
    def is_anonymous(self) -> bool:
        return self._record.is_anonymous

    # ── HTTP helpers ───────────────────────────────────────────────

    def _headers(self, include_auth: bool = True) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if include_auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
                 include_auth: bool = True, timeout: int = 10) -> Dict[str, Any]:
        url = f"{self.api_url}{path}"
        try:
            resp = requests.request(
                method, url,
                headers=self._headers(include_auth=include_auth),
                json=body,
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise IdentityError(f"Network error: {e}")

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail") or resp.text
            except Exception:
                detail = resp.text or f"HTTP {resp.status_code}"
            raise IdentityError(detail, status=resp.status_code)

        # 204 No Content (or any other empty-body 2xx) is a legitimate
        # success response. Return an empty dict instead of trying to
        # parse JSON from nothing — that would otherwise raise here and
        # mask a successful request as "non-JSON response".
        if resp.status_code == 204 or not resp.content:
            return {}

        try:
            return resp.json()
        except Exception:
            raise IdentityError("Server returned non-JSON response")

    def _commit(self, token: str, user_payload: Dict[str, Any]) -> None:
        """Persist a fresh token + user payload returned by the auth API."""
        self._token = token
        self._record = IdentityRecord.from_payload(user_payload)
        self.cred.set_credential(CRED_KEY_TOKEN, token)
        if self._record.user_id:
            self.cred.set_credential(CRED_KEY_USER_ID, self._record.user_id)
        _save_identity_cache(self._record)

    # ── Operations ─────────────────────────────────────────────────

    def ensure_bootstrap(self) -> bool:
        """If no cached token, bootstrap an anonymous account. Returns True
        on success (token is now valid) or False on failure (offline, etc.)."""
        if self._token:
            return True
        try:
            data = self._request(
                "POST", "/api/auth/device-bootstrap",
                body={"device_id": self.device_id, "device_label": self.device_label},
                include_auth=False,
            )
            self._commit(data["session_token"], data["user"])
            logger.info(f"Bootstrapped anonymous user {self._record.user_id}")
            return True
        except IdentityError as e:
            logger.warning(f"device-bootstrap failed: {e}")
            return False

    def refresh_me(self) -> bool:
        """Re-fetch the current identity from the server."""
        if not self._token:
            return False
        try:
            payload = self._request("GET", "/api/auth/me/identity")
            self._record = IdentityRecord.from_payload(payload)
            _save_identity_cache(self._record)
            return True
        except IdentityError as e:
            logger.warning(f"refresh_me failed: {e}")
            return False

    def claim(
        self,
        email: Optional[str],
        phone_number: Optional[str],
        secret: str,
    ) -> str:
        """Claim the anonymous account with email or phone + secret.

        Returns the action string ("upgraded" / "merged" / "login").
        """
        if not self._token:
            self.ensure_bootstrap()
        body = {
            "device_id": self.device_id,
            "secret": secret,
        }
        if email:
            body["email"] = email
        if phone_number:
            body["phone_number"] = phone_number
        data = self._request("POST", "/api/auth/claim", body=body, include_auth=False)
        self._commit(data["session_token"], data["user"])
        return data.get("action", "")

    def login(
        self,
        email: Optional[str],
        phone_number: Optional[str],
        secret: str,
    ) -> None:
        """Sign in on this device with email/phone + secret."""
        body = {
            "device_id": self.device_id,
            "device_label": self.device_label,
            "secret": secret,
        }
        if email:
            body["email"] = email
        if phone_number:
            body["phone_number"] = phone_number
        data = self._request("POST", "/api/auth/login", body=body, include_auth=False)
        self._commit(data["session_token"], data["user"])

    def update_identifiers(
        self,
        current_secret: Optional[str] = None,
        new_email: Optional[str] = None,
        new_phone: Optional[str] = None,
        new_secret: Optional[str] = None,
    ) -> None:
        body: Dict[str, Any] = {}
        if current_secret is not None:
            body["current_secret"] = current_secret
        if new_email is not None:
            body["new_email"] = new_email
        if new_phone is not None:
            body["new_phone"] = new_phone
        if new_secret is not None:
            body["new_secret"] = new_secret
        payload = self._request("POST", "/api/auth/me/identifiers", body=body)
        self._record = IdentityRecord.from_payload(payload)
        _save_identity_cache(self._record)

    def request_recovery(self, email: str) -> bool:
        data = self._request(
            "POST", "/api/auth/recover",
            body={"email": email}, include_auth=False,
        )
        return bool(data.get("sent"))

    def logout(self) -> None:
        """Forget the local token and user_id. The device id is preserved.

        Both CRED_KEY_TOKEN and CRED_KEY_USER_ID are cleared so the next
        launch doesn't repopulate self._record.user_id from a stale cached
        value before ensure_bootstrap() returns a fresh one. The .identity
        cache file is unlinked for the same reason.
        """
        self._token = None
        self.cred.delete_credential(CRED_KEY_TOKEN)
        self.cred.delete_credential(CRED_KEY_USER_ID)
        self._record = IdentityRecord()
        try:
            IDENTITY_CACHE_FILE.unlink(missing_ok=True)
        except Exception:
            pass


# ── Module-level singleton accessor ────────────────────────────────

_singleton: Optional[DesktopIdentity] = None


def identity() -> DesktopIdentity:
    """Return the process-wide DesktopIdentity instance, creating it lazily."""
    global _singleton
    if _singleton is None:
        _singleton = DesktopIdentity()
    return _singleton
