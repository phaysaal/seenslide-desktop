"""Main application starter for SeenSlide.

This is the entry point for the presentation PC. It will:
1. Check if admin user exists
2. If not, prompt for initial admin password setup
3. Prompt for session ID (existing or new)
4. Start the admin server
"""

import logging
import argparse
import sys
import getpass
from pathlib import Path
from typing import Optional, Tuple

from core.models.user import User
from core.auth.auth_utils import AuthUtils
from core.session.local_session_manager import LocalSessionManager
from modules.storage.user_storage import UserStorage
from modules.admin.admin_server import AdminServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_initial_admin(
    storage_path: str,
    non_interactive_username: Optional[str] = None,
    non_interactive_password: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Setup initial admin user if none exists.

    Args:
        storage_path: Path to storage directory
        non_interactive_username: Username for non-interactive mode (optional)
        non_interactive_password: Password for non-interactive mode (optional)

    Returns:
        Tuple of (success, username, password_hash)
    """
    user_storage = UserStorage(
        db_path=str(Path(storage_path) / "db" / "seenslide.db")
    )

    # Check if any users exist
    users = user_storage.get_all_users()
    if len(users) > 0:
        logger.info("Admin user already exists")
        # Return first admin user's credentials
        first_admin = users[0]
        return True, first_admin.username, first_admin.password_hash

    # Non-interactive mode
    if non_interactive_username and non_interactive_password:
        logger.info(f"Creating admin user in non-interactive mode: {non_interactive_username}")

        # Validate password strength
        is_valid, error_msg = AuthUtils.validate_password_strength(non_interactive_password)
        if not is_valid:
            logger.error(f"Password validation failed: {error_msg}")
            return False, None, None

        password_hash = AuthUtils.hash_password(non_interactive_password)

        admin_user = User(
            username=non_interactive_username,
            password_hash=password_hash,
            role="admin"
        )

        if user_storage.create_user(admin_user):
            logger.info(f"✓ Admin user '{non_interactive_username}' created successfully")
            return True, non_interactive_username, password_hash
        else:
            logger.error("Failed to create admin user")
            return False, None, None

    # Interactive mode (prompt for credentials)
    print("\n" + "="*70)
    print("INITIAL ADMIN SETUP")
    print("="*70)
    print("\nNo admin user found. Please create the initial admin account.\n")

    username = input("Enter admin username (default: admin): ").strip() or "admin"

    while True:
        password = getpass.getpass("Enter admin password: ")
        password_confirm = getpass.getpass("Confirm admin password: ")

        if password != password_confirm:
            print("Error: Passwords do not match. Please try again.\n")
            continue

        # Validate password strength
        is_valid, error_msg = AuthUtils.validate_password_strength(password)
        if not is_valid:
            print(f"Error: {error_msg}\n")
            print("Password requirements:")
            print("  - At least 8 characters long")
            print("  - At least one uppercase letter")
            print("  - At least one lowercase letter")
            print("  - At least one digit\n")
            continue

        break

    # Create admin user
    password_hash = AuthUtils.hash_password(password)

    admin_user = User(
        username=username,
        password_hash=password_hash,
        role="admin"
    )

    if user_storage.create_user(admin_user):
        print(f"\n✓ Admin user '{username}' created successfully!")
        print(f"  User ID: {admin_user.user_id}")
        print()
        return True, username, password_hash
    else:
        print(f"\n✗ Failed to create admin user")
        return False, None, None


def setup_session_id(storage_path: str, admin_username: str, admin_password_hash: str) -> bool:
    """Setup session ID for cloud registration.

    Args:
        storage_path: Path to storage directory
        admin_username: Admin username
        admin_password_hash: Admin password hash

    Returns:
        True if successful, False otherwise
    """
    local_session_manager = LocalSessionManager(config_dir=Path(storage_path))

    # Check if session ID already exists locally
    existing_session_id = local_session_manager.load_session_id()

    if existing_session_id:
        print(f"\n✓ Found existing session ID: {existing_session_id}")
        print("  This session will be used for cloud registration.")
        return True

    # No local session ID found - prompt user
    print("\n" + "="*70)
    print("SESSION ID SETUP")
    print("="*70)
    print("\nNo local session ID found.")
    print("\nOptions:")
    print("  1. Create a NEW session (recommended for first-time setup)")
    print("  2. Use an EXISTING session from another machine")
    print()

    while True:
        choice = input("Enter choice (1 or 2): ").strip()
        if choice in ["1", "2"]:
            break
        print("Invalid choice. Please enter 1 or 2.")

    if choice == "1":
        # New session - will be created by admin server and saved
        print("\n✓ A new session will be created and registered in the cloud.")
        print(f"  Admin credentials ({admin_username}) will be linked to this session.")
        print()
        return True
    else:
        # Existing session - prompt for session ID
        print("\nTo use an existing session from another machine:")
        print("  - Enter the session ID from your other machine")
        print("  - Your admin credentials will be verified with the cloud")
        print()

        session_id = input("Enter session ID: ").strip().upper()

        if not session_id:
            print("✗ Session ID cannot be empty.")
            return False

        # Save session ID locally (will be verified by admin server on startup)
        local_session_manager.save_session_id(session_id)
        print(f"\n✓ Session ID '{session_id}' will be verified with cloud on startup.")
        print()
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SeenSlide Application - Start Admin Server"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--admin-port",
        type=int,
        default=8081,
        help="Admin server port (default: 8081)"
    )
    parser.add_argument(
        "--viewer-port",
        type=int,
        default=8080,
        help="Viewer server port (default: 8080)"
    )
    parser.add_argument(
        "--storage",
        default="/tmp/seenslide",
        help="Storage path (default: /tmp/seenslide)"
    )
    parser.add_argument(
        "--admin-username",
        help="Admin username for non-interactive setup"
    )
    parser.add_argument(
        "--admin-password",
        help="Admin password for non-interactive setup"
    )

    args = parser.parse_args()

    # Setup initial admin if needed
    success, admin_username, admin_password_hash = setup_initial_admin(
        args.storage,
        non_interactive_username=args.admin_username,
        non_interactive_password=args.admin_password
    )
    if not success:
        logger.error("Failed to setup admin user")
        sys.exit(1)

    # Setup session ID
    if not setup_session_id(args.storage, admin_username, admin_password_hash):
        logger.error("Failed to setup session ID")
        sys.exit(1)

    # Start admin server
    print("="*70)
    print("Starting SeenSlide Admin Server")
    print("="*70)
    print()

    server = AdminServer(
        storage_path=args.storage,
        host=args.host,
        port=args.admin_port,
        viewer_port=args.viewer_port,
        admin_username=admin_username,
        admin_password_hash=admin_password_hash
    )
    server.run()


if __name__ == "__main__":
    main()
