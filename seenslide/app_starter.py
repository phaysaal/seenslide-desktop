"""Main application starter for SeenSlide.

This is the entry point for the presentation PC. It will:
1. Check if admin user exists
2. If not, prompt for initial admin password setup
3. Start the admin server
"""

import logging
import argparse
import sys
import getpass
from pathlib import Path

from core.models.user import User
from core.auth.auth_utils import AuthUtils
from modules.storage.user_storage import UserStorage
from modules.admin.admin_server import AdminServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_initial_admin(storage_path: str) -> bool:
    """Setup initial admin user if none exists.

    Args:
        storage_path: Path to storage directory

    Returns:
        True if setup successful or admin exists, False otherwise
    """
    user_storage = UserStorage(
        db_path=str(Path(storage_path) / "db" / "seenslide.db")
    )

    # Check if any users exist
    users = user_storage.get_all_users()
    if len(users) > 0:
        logger.info("Admin user already exists")
        return True

    # Prompt for initial admin setup
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
        return True
    else:
        print(f"\n✗ Failed to create admin user")
        return False


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

    args = parser.parse_args()

    # Setup initial admin if needed
    if not setup_initial_admin(args.storage):
        logger.error("Failed to setup admin user")
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
        viewer_port=args.viewer_port
    )
    server.run()


if __name__ == "__main__":
    main()
