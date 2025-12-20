"""Console-based user management tool for SeenSlide.

This tool allows local administrators to manage user accounts:
- Create new users
- Change passwords
- List users
- Delete users
- Activate/deactivate users
"""

import argparse
import sys
import logging
import getpass
from pathlib import Path
from datetime import datetime

from core.models.user import User
from core.auth.auth_utils import AuthUtils
from modules.storage.user_storage import UserStorage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def cmd_create_user(args, storage: UserStorage):
    """Create a new user account.

    Args:
        args: Command-line arguments
        storage: User storage instance
    """
    username = args.username

    # Check if user already exists
    if storage.user_exists(username):
        logger.error(f"Error: User '{username}' already exists")
        sys.exit(1)

    # Get password
    password = getpass.getpass("Enter password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        logger.error("Error: Passwords do not match")
        sys.exit(1)

    # Validate password strength
    is_valid, error_msg = AuthUtils.validate_password_strength(password)
    if not is_valid:
        logger.error(f"Error: {error_msg}")
        sys.exit(1)

    # Hash password
    password_hash = AuthUtils.hash_password(password)

    # Create user object
    user = User(
        username=username,
        password_hash=password_hash,
        email=args.email or "",
        full_name=args.name or "",
        role=args.role or "admin"
    )

    # Save to database
    if storage.create_user(user):
        logger.info(f"✓ User '{username}' created successfully")
        logger.info(f"  User ID: {user.user_id}")
        logger.info(f"  Role: {user.role}")
    else:
        logger.error(f"Error: Failed to create user '{username}'")
        sys.exit(1)


def cmd_change_password(args, storage: UserStorage):
    """Change user password.

    Args:
        args: Command-line arguments
        storage: User storage instance
    """
    username = args.username

    # Check if user exists
    user = storage.get_user_by_username(username)
    if not user:
        logger.error(f"Error: User '{username}' not found")
        sys.exit(1)

    # Get new password
    password = getpass.getpass("Enter new password: ")
    password_confirm = getpass.getpass("Confirm new password: ")

    if password != password_confirm:
        logger.error("Error: Passwords do not match")
        sys.exit(1)

    # Validate password strength
    is_valid, error_msg = AuthUtils.validate_password_strength(password)
    if not is_valid:
        logger.error(f"Error: {error_msg}")
        sys.exit(1)

    # Update password
    user.password_hash = AuthUtils.hash_password(password)

    if storage.update_user(user):
        logger.info(f"✓ Password changed successfully for '{username}'")
    else:
        logger.error(f"Error: Failed to change password for '{username}'")
        sys.exit(1)


def cmd_list_users(args, storage: UserStorage):
    """List all users.

    Args:
        args: Command-line arguments
        storage: User storage instance
    """
    users = storage.get_all_users()

    if not users:
        logger.info("No users found")
        return

    logger.info("\nUsers:")
    logger.info("-" * 80)
    logger.info(f"{'Username':<20} {'Role':<10} {'Active':<8} {'Last Login':<20}")
    logger.info("-" * 80)

    for user in users:
        last_login = "Never"
        if user.last_login:
            last_login = datetime.fromtimestamp(user.last_login).strftime('%Y-%m-%d %H:%M:%S')

        status = "Yes" if user.is_active else "No"
        logger.info(f"{user.username:<20} {user.role:<10} {status:<8} {last_login:<20}")

    logger.info("-" * 80)
    logger.info(f"Total: {len(users)} users\n")


def cmd_delete_user(args, storage: UserStorage):
    """Delete a user.

    Args:
        args: Command-line arguments
        storage: User storage instance
    """
    username = args.username

    # Check if user exists
    user = storage.get_user_by_username(username)
    if not user:
        logger.error(f"Error: User '{username}' not found")
        sys.exit(1)

    # Confirm deletion
    if not args.force:
        confirm = input(f"Are you sure you want to delete user '{username}'? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Deletion cancelled")
            return

    # Delete user
    if storage.delete_user(user.user_id):
        logger.info(f"✓ User '{username}' deleted successfully")
    else:
        logger.error(f"Error: Failed to delete user '{username}'")
        sys.exit(1)


def cmd_activate_user(args, storage: UserStorage):
    """Activate a user account.

    Args:
        args: Command-line arguments
        storage: User storage instance
    """
    username = args.username

    # Check if user exists
    user = storage.get_user_by_username(username)
    if not user:
        logger.error(f"Error: User '{username}' not found")
        sys.exit(1)

    if user.is_active:
        logger.info(f"User '{username}' is already active")
        return

    user.is_active = True
    if storage.update_user(user):
        logger.info(f"✓ User '{username}' activated successfully")
    else:
        logger.error(f"Error: Failed to activate user '{username}'")
        sys.exit(1)


def cmd_deactivate_user(args, storage: UserStorage):
    """Deactivate a user account.

    Args:
        args: Command-line arguments
        storage: User storage instance
    """
    username = args.username

    # Check if user exists
    user = storage.get_user_by_username(username)
    if not user:
        logger.error(f"Error: User '{username}' not found")
        sys.exit(1)

    if not user.is_active:
        logger.info(f"User '{username}' is already inactive")
        return

    user.is_active = False
    if storage.update_user(user):
        logger.info(f"✓ User '{username}' deactivated successfully")
    else:
        logger.error(f"Error: Failed to deactivate user '{username}'")
        sys.exit(1)


def main():
    """Main entry point for user management CLI."""
    parser = argparse.ArgumentParser(
        description="SeenSlide User Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Global options
    parser.add_argument(
        "--db",
        default="/tmp/seenslide/db/seenslide.db",
        help="Path to database file (default: /tmp/seenslide/db/seenslide.db)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(
        title="commands",
        description="Available commands",
        dest="command"
    )

    # Create user command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new user"
    )
    create_parser.add_argument("username", help="Username")
    create_parser.add_argument("--email", help="Email address")
    create_parser.add_argument("--name", help="Full name")
    create_parser.add_argument("--role", default="admin", help="User role (default: admin)")
    create_parser.set_defaults(func=cmd_create_user)

    # Change password command
    passwd_parser = subparsers.add_parser(
        "passwd",
        help="Change user password"
    )
    passwd_parser.add_argument("username", help="Username")
    passwd_parser.set_defaults(func=cmd_change_password)

    # List users command
    list_parser = subparsers.add_parser(
        "list",
        help="List all users"
    )
    list_parser.set_defaults(func=cmd_list_users)

    # Delete user command
    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a user"
    )
    delete_parser.add_argument("username", help="Username")
    delete_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")
    delete_parser.set_defaults(func=cmd_delete_user)

    # Activate user command
    activate_parser = subparsers.add_parser(
        "activate",
        help="Activate a user account"
    )
    activate_parser.add_argument("username", help="Username")
    activate_parser.set_defaults(func=cmd_activate_user)

    # Deactivate user command
    deactivate_parser = subparsers.add_parser(
        "deactivate",
        help="Deactivate a user account"
    )
    deactivate_parser.add_argument("username", help="Username")
    deactivate_parser.set_defaults(func=cmd_deactivate_user)

    # Parse arguments
    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    # Initialize storage
    storage = UserStorage(db_path=args.db)

    # Execute command
    args.func(args, storage)


if __name__ == "__main__":
    main()
