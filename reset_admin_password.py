#!/usr/bin/env python3
"""Reset admin password or create admin user with known password."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.storage.user_storage import UserStorage
from core.models.user import User
from core.auth.auth_utils import AuthUtils


def main():
    """Reset or create admin user with password 'admin123'."""
    print("=" * 70)
    print("ADMIN PASSWORD RESET UTILITY")
    print("=" * 70)

    # Initialize storage
    storage_path = "/tmp/seenslide/db/seenslide.db"
    print(f"\nUsing database: {storage_path}")

    storage = UserStorage(storage_path)

    # Check if admin user exists
    admin_user = storage.get_user_by_username("admin")

    if admin_user:
        print(f"\n✓ Found existing admin user:")
        print(f"  User ID: {admin_user.user_id}")
        print(f"  Username: {admin_user.username}")
        print(f"  Email: {admin_user.email}")
        print(f"  Role: {admin_user.role}")
        print(f"  Active: {admin_user.is_active}")

        # Reset password
        print("\nResetting password to 'admin123'...")
        new_password_hash = AuthUtils.hash_password("admin123")

        # Update password
        admin_user.password_hash = new_password_hash
        success = storage.update_user(admin_user)

        if success:
            print("✅ Password reset successfully!")
            print("\nYou can now login with:")
            print("  Username: admin")
            print("  Password: admin123")
        else:
            print("❌ Failed to reset password")
            return 1

    else:
        print("\n✗ No admin user found. Creating one...")

        # Create new admin user
        password_hash = AuthUtils.hash_password("admin123")

        admin_user = User(
            username="admin",
            email="admin@seenslide.local",
            password_hash=password_hash,
            role="admin"
        )

        success = storage.create_user(admin_user)

        if success:
            print("✅ Admin user created successfully!")
            print("\nLogin credentials:")
            print("  Username: admin")
            print("  Password: admin123")
            print(f"  User ID: {admin_user.user_id}")
        else:
            print("❌ Failed to create admin user")
            return 1

    print("\n" + "=" * 70)
    print("✅ DONE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
