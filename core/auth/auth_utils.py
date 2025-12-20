"""Authentication utilities for password hashing and token generation."""

import hashlib
import secrets
import hmac
from typing import Tuple, Optional
from datetime import datetime, timedelta


class AuthUtils:
    """Utilities for authentication and password management."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using PBKDF2-SHA256.

        Args:
            password: Plain text password

        Returns:
            Hashed password in format: salt$hash
        """
        salt = secrets.token_hex(32)
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # iterations
        )
        return f"{salt}${pwd_hash.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash.

        Args:
            password: Plain text password to verify
            password_hash: Stored password hash in format: salt$hash

        Returns:
            True if password matches, False otherwise
        """
        try:
            salt, stored_hash = password_hash.split('$')
            pwd_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return hmac.compare_digest(pwd_hash.hex(), stored_hash)
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def generate_session_token() -> str:
        """Generate a secure random session token.

        Returns:
            Random token string
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def validate_password_strength(password: str) -> Tuple[bool, str]:
        """Validate password strength.

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        return True, ""


class SessionManager:
    """Manages user sessions and tokens."""

    def __init__(self):
        """Initialize session manager."""
        self._sessions = {}  # token -> (user_id, expiry)
        self._session_duration = timedelta(hours=24)

    def create_session(self, user_id: str) -> str:
        """Create a new session for a user.

        Args:
            user_id: User ID

        Returns:
            Session token
        """
        token = AuthUtils.generate_session_token()
        expiry = datetime.now() + self._session_duration
        self._sessions[token] = (user_id, expiry)
        return token

    def validate_session(self, token: str) -> Optional[str]:
        """Validate a session token.

        Args:
            token: Session token to validate

        Returns:
            User ID if valid, None otherwise
        """
        if token not in self._sessions:
            return None

        user_id, expiry = self._sessions[token]
        if datetime.now() > expiry:
            # Session expired
            del self._sessions[token]
            return None

        return user_id

    def invalidate_session(self, token: str) -> None:
        """Invalidate a session (logout).

        Args:
            token: Session token to invalidate
        """
        if token in self._sessions:
            del self._sessions[token]

    def cleanup_expired_sessions(self) -> None:
        """Remove all expired sessions."""
        now = datetime.now()
        expired = [
            token for token, (_, expiry) in self._sessions.items()
            if now > expiry
        ]
        for token in expired:
            del self._sessions[token]
