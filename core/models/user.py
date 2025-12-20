"""User model for authentication."""

from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime


@dataclass
class User:
    """User account for admin access.

    Attributes:
        user_id: Unique identifier for the user
        username: Username for login
        password_hash: Hashed password (never store plain text)
        email: Optional email address
        full_name: Optional full name
        is_active: Whether the user account is active
        created_at: When the account was created
        last_login: Last login timestamp
        role: User role (admin, operator, etc.)
    """
    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    password_hash: str = ""
    email: str = ""
    full_name: str = ""
    is_active: bool = True
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    last_login: Optional[float] = None
    role: str = "admin"

    def to_dict(self, include_password=False):
        """Convert to dictionary.

        Args:
            include_password: Whether to include password hash (default: False)

        Returns:
            Dictionary representation
        """
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "role": self.role,
        }
        if include_password:
            data["password_hash"] = self.password_hash
        return data
