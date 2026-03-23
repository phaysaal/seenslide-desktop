"""User storage provider for authentication."""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, List
import json
from datetime import datetime

from core.models.user import User

logger = logging.getLogger(__name__)


class UserStorage:
    """Storage provider for user accounts."""

    def __init__(self, db_path: str = "/tmp/seenslide/db/seenslide.db"):
        """Initialize user storage.

        Args:
            db_path: Path to SQLite database
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None
        self._initialize_db()

    def _initialize_db(self):
        """Initialize database connection and create tables."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"User storage initialized at: {self._db_path}")

    def _create_tables(self):
        """Create user tables if they don't exist."""
        cursor = self._conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                full_name TEXT,
                is_active INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                last_login REAL,
                role TEXT DEFAULT 'admin'
            )
        """)

        # Create index on username for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username
            ON users(username)
        """)

        self._conn.commit()

    def create_user(self, user: User) -> bool:
        """Create a new user.

        Args:
            user: User object to create

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                INSERT INTO users (
                    user_id, username, password_hash, email, full_name,
                    is_active, created_at, last_login, role
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user.user_id,
                user.username,
                user.password_hash,
                user.email,
                user.full_name,
                1 if user.is_active else 0,
                user.created_at,
                user.last_login,
                user.role
            ))
            self._conn.commit()
            logger.info(f"Created user: {user.username}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Failed to create user (username exists): {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return False

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username.

        Args:
            username: Username to look up

        Returns:
            User object or None if not found
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_user(row)
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID.

        Args:
            user_id: User ID to look up

        Returns:
            User object or None if not found
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_user(row)
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None

    def get_all_users(self) -> List[User]:
        """Get all users.

        Returns:
            List of User objects
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [self._row_to_user(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            return []

    def update_user(self, user: User) -> bool:
        """Update user information.

        Args:
            user: User object with updated information

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("""
                UPDATE users SET
                    username = ?,
                    password_hash = ?,
                    email = ?,
                    full_name = ?,
                    is_active = ?,
                    last_login = ?,
                    role = ?
                WHERE user_id = ?
            """, (
                user.username,
                user.password_hash,
                user.email,
                user.full_name,
                1 if user.is_active else 0,
                user.last_login,
                user.role,
                user.user_id
            ))
            self._conn.commit()
            logger.info(f"Updated user: {user.username}")
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return False

    def update_last_login(self, user_id: str) -> bool:
        """Update user's last login time.

        Args:
            user_id: User ID

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE users SET last_login = ? WHERE user_id = ?",
                (datetime.now().timestamp(), user_id)
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update last login: {e}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """Delete a user.

        Args:
            user_id: User ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self._conn.commit()
            logger.info(f"Deleted user: {user_id}")
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

    def user_exists(self, username: str) -> bool:
        """Check if a user exists.

        Args:
            username: Username to check

        Returns:
            True if user exists, False otherwise
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE username = ?",
            (username,)
        )
        return cursor.fetchone()[0] > 0

    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Convert database row to User object.

        Args:
            row: Database row

        Returns:
            User object
        """
        return User(
            user_id=row['user_id'],
            username=row['username'],
            password_hash=row['password_hash'],
            email=row['email'] or "",
            full_name=row['full_name'] or "",
            is_active=bool(row['is_active']),
            created_at=row['created_at'],
            last_login=row['last_login'],
            role=row['role'] or "admin"
        )

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
