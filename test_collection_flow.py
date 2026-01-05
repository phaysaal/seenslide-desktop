#!/usr/bin/env python3
"""Simple test script for collection flow."""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.session.collection_registry import CollectionRegistry
from core.session.credential_manager import CredentialManager, get_device_fingerprint
import bcrypt


def test_collection_registry():
    """Test collection registry operations."""
    logger.info("=" * 60)
    logger.info("Testing Collection Registry")
    logger.info("=" * 60)

    registry = CollectionRegistry()

    # Check if collections exist
    if registry.has_collections():
        logger.info(f"✅ Found {len(registry.collections)} existing collection(s)")

        # Show current collection
        current = registry.get_current_collection()
        if current:
            logger.info(f"✅ Current collection: {current.name}")
            logger.info(f"   - Local ID: {current.collection_id}")
            logger.info(f"   - Cloud ID: {current.cloud_collection_id}")
            logger.info(f"   - Owner: {current.owner_username}")
            logger.info(f"   - Is Owner: {current.is_owner}")
            logger.info(f"   - Has Password: {current.has_password}")
            if current.alias:
                logger.info(f"   - Alias: {current.alias}")
        else:
            logger.error("❌ No current collection set!")

        # List all collections
        logger.info(f"\n📚 All collections:")
        for i, collection in enumerate(registry.list_collections(), 1):
            logger.info(f"   {i}. {collection.name} ({collection.cloud_collection_id})")
    else:
        logger.info("ℹ️  No collections found (first-time user)")
        logger.info("   The FirstCollectionDialog should appear when you run the app")

    return registry


def test_credential_manager():
    """Test credential manager."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Credential Manager")
    logger.info("=" * 60)

    cred_manager = CredentialManager()

    if cred_manager.keyring_available:
        logger.info("✅ System keyring available (secure storage)")
    else:
        logger.info("⚠️  Keyring not available, using fallback storage")

    # Check device fingerprint
    fingerprint = get_device_fingerprint()
    logger.info(f"🔑 Device fingerprint: {fingerprint}")

    return cred_manager


def test_password_hashing():
    """Test password hashing."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Password Hashing")
    logger.info("=" * 60)

    test_password = "test_password_123"

    # Hash password
    password_hash = bcrypt.hashpw(
        test_password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    logger.info(f"✅ Password hashed successfully")
    logger.info(f"   Hash length: {len(password_hash)} chars")

    # Verify password
    is_valid = bcrypt.checkpw(
        test_password.encode('utf-8'),
        password_hash.encode('utf-8')
    )

    if is_valid:
        logger.info("✅ Password verification works")
    else:
        logger.error("❌ Password verification failed!")

    # Test wrong password
    is_valid = bcrypt.checkpw(
        "wrong_password".encode('utf-8'),
        password_hash.encode('utf-8')
    )

    if not is_valid:
        logger.info("✅ Wrong password correctly rejected")
    else:
        logger.error("❌ Wrong password incorrectly accepted!")


def test_collection_creation_simulation():
    """Simulate first-time collection creation."""
    logger.info("\n" + "=" * 60)
    logger.info("Simulating First-Time Collection Creation")
    logger.info("=" * 60)

    registry = CollectionRegistry()
    cred_manager = CredentialManager()

    # Check if we already have collections
    if registry.has_collections():
        logger.info("ℹ️  Collections already exist, skipping simulation")
        logger.info("   To test first-time flow, delete:")
        logger.info(f"   - {registry.registry_path}")
        return

    # Simulate user input
    collection_name = "Test Collection 2026"
    username = "test@example.com"
    password = "secure_password_123"

    logger.info(f"📝 Simulated user input:")
    logger.info(f"   Collection: {collection_name}")
    logger.info(f"   Username: {username}")
    logger.info(f"   Password: {'*' * len(password)}")

    # Hash password
    password_hash = bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    logger.info(f"✅ Password hashed")

    # Simulate cloud collection creation (we'll use a fake ID)
    cloud_collection_id = "TEST-1234"  # In real app, this comes from cloud API

    logger.info(f"☁️  Simulated cloud collection creation: {cloud_collection_id}")

    # Add to registry
    collection = registry.add_collection(
        cloud_collection_id=cloud_collection_id,
        name=collection_name,
        owner_username=username,
        is_owner=True,
        access_level="owner",
        has_password=True
    )

    logger.info(f"✅ Collection added to registry: {collection.collection_id}")

    # Store credentials
    cred_manager.store_password_hash(cloud_collection_id, password_hash)
    logger.info(f"✅ Password stored securely")

    # Verify storage
    stored_hash = cred_manager.get_password_hash(cloud_collection_id)
    if stored_hash:
        logger.info(f"✅ Password retrieved from storage")

        # Verify it matches
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            logger.info(f"✅ Password verification successful")
        else:
            logger.error(f"❌ Password verification failed!")
    else:
        logger.error(f"❌ Failed to retrieve password!")

    logger.info(f"\n✅ Simulation complete! Collection saved to:")
    logger.info(f"   {registry.registry_path}")


def main():
    """Run all tests."""
    try:
        # Test 1: Collection Registry
        registry = test_collection_registry()

        # Test 2: Credential Manager
        cred_manager = test_credential_manager()

        # Test 3: Password Hashing
        test_password_hashing()

        # Test 4: Simulate collection creation (only if no collections exist)
        test_collection_creation_simulation()

        logger.info("\n" + "=" * 60)
        logger.info("✅ All tests completed!")
        logger.info("=" * 60)

        # Summary
        logger.info("\n📊 Summary:")
        logger.info(f"   Collections: {len(registry.collections)}")
        if registry.has_collections():
            current = registry.get_current_collection()
            if current:
                logger.info(f"   Current: {current.name} ({current.cloud_collection_id})")

        logger.info("\n🚀 Next steps:")
        logger.info("   1. Run the SeenSlide GUI app")
        if not registry.has_collections():
            logger.info("   2. FirstCollectionDialog should appear")
            logger.info("   3. Enter collection name and username")
            logger.info("   4. Optionally set a password")
        else:
            logger.info("   2. App should load existing collection")
            logger.info("   3. Direct Talk window should show collection info")
            logger.info("   4. All talks will be added to the same collection!")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
