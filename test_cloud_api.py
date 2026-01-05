#!/usr/bin/env python3
"""Test script for cloud collection API endpoints.

Tests the backend API implementation against the spec.
"""

import sys
import time
import bcrypt
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Test configuration
API_BASE = "http://localhost:8081/api/cloud"
TEST_COLLECTION_NAME = "Test ML Conference 2026"
TEST_USERNAME = "test@example.com"
TEST_PASSWORD = "test_password_123"
TEST_ALIAS = "test-ml-conference"


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def test_create_collection():
    """Test POST /session/create endpoint."""
    print("\n" + "=" * 70)
    print("TEST 1: Create Collection")
    print("=" * 70)

    password_hash = hash_password(TEST_PASSWORD)

    payload = {
        "name": TEST_COLLECTION_NAME,
        "presenter_name": "John Doe",
        "description": "Machine learning presentations for testing",
        "is_private": False,
        "max_slides": 100,
        "admin_username": TEST_USERNAME,
        "admin_password_hash": password_hash
    }

    print(f"Creating collection with username: {TEST_USERNAME}")
    response = requests.post(f"{API_BASE}/session/create", json=payload)

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("session_id"):
            print(f"✅ Collection created successfully: {data['session_id']}")
            return data["session_id"]
        else:
            print("❌ Collection creation failed: Invalid response format")
            return None
    else:
        print(f"❌ Collection creation failed: HTTP {response.status_code}")
        return None


def test_get_collection_info(collection_id: str):
    """Test GET /session/{id} endpoint."""
    print("\n" + "=" * 70)
    print("TEST 2: Get Collection Info")
    print("=" * 70)

    print(f"Fetching info for collection: {collection_id}")
    response = requests.get(f"{API_BASE}/session/{collection_id}")

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        if data.get("session_id") == collection_id:
            print(f"✅ Collection info retrieved successfully")
            print(f"   Name: {data.get('name')}")
            print(f"   Owner: {data.get('presenter_name')}")
            print(f"   Has Password: {data.get('has_password')}")
            return True
        else:
            print("❌ Failed to retrieve collection info: Invalid response")
            return False
    else:
        print(f"❌ Failed to retrieve collection info: HTTP {response.status_code}")
        return False


def test_verify_password(collection_id: str, password: str, should_succeed: bool = True):
    """Test POST /session/{id}/verify endpoint."""
    print("\n" + "=" * 70)
    print(f"TEST 3: Verify Password (should {'succeed' if should_succeed else 'fail'})")
    print("=" * 70)

    payload = {"password": password}

    print(f"Verifying password for collection: {collection_id}")
    response = requests.post(f"{API_BASE}/session/{collection_id}/verify", json=payload)

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        verified = data.get("verified", False)

        if verified and should_succeed:
            print(f"✅ Password verified successfully")
            print(f"   Session ID: {data.get('session_id')}")
            print(f"   Owner: {data.get('owner_username')}")
            print(f"   Session Token: {data.get('session_token')[:50]}..." if data.get('session_token') else "")
            return data.get("session_token")
        elif not verified and not should_succeed:
            print(f"✅ Password correctly rejected")
            return None
        else:
            print(f"❌ Unexpected verification result: {verified}")
            return None
    else:
        print(f"❌ Password verification failed: HTTP {response.status_code}")
        return None


def test_update_alias(collection_id: str, alias: str):
    """Test POST /session/{id}/alias endpoint."""
    print("\n" + "=" * 70)
    print("TEST 4: Update Collection Alias")
    print("=" * 70)

    payload = {"alias": alias}

    print(f"Setting alias '{alias}' for collection: {collection_id}")
    response = requests.post(f"{API_BASE}/session/{collection_id}/alias", json=payload)

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("alias") == alias:
            print(f"✅ Alias updated successfully: {alias}")
            return True
        else:
            print("❌ Alias update failed: Invalid response")
            return False
    else:
        print(f"❌ Alias update failed: HTTP {response.status_code}")
        return False


def test_verify_by_alias(alias: str, password: str):
    """Test verifying collection by alias instead of ID."""
    print("\n" + "=" * 70)
    print("TEST 5: Verify by Alias")
    print("=" * 70)

    payload = {"password": password}

    print(f"Verifying password using alias: {alias}")
    response = requests.post(f"{API_BASE}/session/{alias}/verify", json=payload)

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        if data.get("verified"):
            print(f"✅ Verification by alias successful")
            return True
        else:
            print("❌ Verification by alias failed")
            return False
    else:
        print(f"❌ Verification by alias failed: HTTP {response.status_code}")
        return False


def test_update_password(collection_id: str, new_password: str):
    """Test POST /session/{id}/password endpoint."""
    print("\n" + "=" * 70)
    print("TEST 6: Update Collection Password")
    print("=" * 70)

    new_password_hash = hash_password(new_password)

    payload = {
        "admin_username": TEST_USERNAME,
        "new_password_hash": new_password_hash
    }

    print(f"Updating password for collection: {collection_id}")
    response = requests.post(f"{API_BASE}/session/{collection_id}/password", json=payload)

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print(f"✅ Password updated successfully")
            return True
        else:
            print("❌ Password update failed: Invalid response")
            return False
    else:
        print(f"❌ Password update failed: HTTP {response.status_code}")
        return False


def test_start_talk(collection_id: str):
    """Test POST /session/{id}/start-talk endpoint."""
    print("\n" + "=" * 70)
    print("TEST 7: Start Talk in Collection")
    print("=" * 70)

    payload = {
        "title": "Introduction to Deep Learning",
        "description": "Basics of neural networks and backpropagation"
    }

    print(f"Creating talk in collection: {collection_id}")
    response = requests.post(f"{API_BASE}/session/{collection_id}/start-talk", json=payload)

    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("talk"):
            print(f"✅ Talk created successfully")
            talk = data["talk"]
            print(f"   Talk ID: {talk.get('talk_id')}")
            print(f"   Title: {talk.get('title')}")
            return talk.get("talk_id")
        else:
            print("❌ Talk creation failed: Invalid response")
            return None
    else:
        print(f"❌ Talk creation failed: HTTP {response.status_code}")
        return None


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("SeenSlide Cloud Collection API Tests")
    print("=" * 70)
    print(f"\nAPI Base URL: {API_BASE}")
    print(f"Test Username: {TEST_USERNAME}")
    print(f"Test Password: {TEST_PASSWORD}")
    print(f"Test Alias: {TEST_ALIAS}")

    print("\nNOTE: Make sure the admin server is running on port 8081")
    print("      Run: python seenslide.py admin --port 8081\n")

    input("Press Enter to start tests...")

    # Test 1: Create collection
    collection_id = test_create_collection()
    if not collection_id:
        print("\n❌ FAILED: Could not create collection. Aborting tests.")
        return 1

    # Test 2: Get collection info
    if not test_get_collection_info(collection_id):
        print("\n⚠️  WARNING: Failed to get collection info")

    # Test 3: Verify correct password
    session_token = test_verify_password(collection_id, TEST_PASSWORD, should_succeed=True)
    if not session_token:
        print("\n⚠️  WARNING: Failed to verify correct password")

    # Test 3b: Verify wrong password
    test_verify_password(collection_id, "wrong_password", should_succeed=False)

    # Test 4: Update alias
    if not test_update_alias(collection_id, TEST_ALIAS):
        print("\n⚠️  WARNING: Failed to update alias")

    # Test 5: Verify by alias
    if not test_verify_by_alias(TEST_ALIAS, TEST_PASSWORD):
        print("\n⚠️  WARNING: Failed to verify by alias")

    # Test 6: Update password
    new_password = "new_password_456"
    if test_update_password(collection_id, new_password):
        # Test with new password
        test_verify_password(collection_id, new_password, should_succeed=True)
        # Old password should fail
        test_verify_password(collection_id, TEST_PASSWORD, should_succeed=False)

    # Test 7: Start talk
    talk_id = test_start_talk(collection_id)
    if not talk_id:
        print("\n⚠️  WARNING: Failed to create talk")

    print("\n" + "=" * 70)
    print("All Tests Completed!")
    print("=" * 70)
    print(f"\n✅ Created Collection: {collection_id}")
    print(f"✅ Set Alias: {TEST_ALIAS}")
    print(f"✅ Created Talk: {talk_id if talk_id else 'N/A'}")
    print(f"\nYou can now test the desktop client with:")
    print(f"  Collection ID/Alias: {TEST_ALIAS} or {collection_id}")
    print(f"  Password: new_password_456")

    return 0


if __name__ == "__main__":
    sys.exit(main())
