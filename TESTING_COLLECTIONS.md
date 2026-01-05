# Testing Collection Management - Complete Guide

## Overview

This guide walks through testing the complete collection management system, including:
- Backend API endpoints
- Desktop client integration
- Multi-device access
- Collection sharing

---

## Phase 1: Test Backend API

### Start Admin Server

```bash
# Terminal 1: Start admin server
python seenslide.py admin --port 8081
```

Wait for the server to start. You should see:
```
SeenSlide Admin Server Starting
======================================================================
Access the admin panel at:
  http://localhost:8081  (this machine)
```

### Run Backend Tests

```bash
# Terminal 2: Run automated tests
python test_cloud_api.py
```

Expected output:
```
SeenSlide Cloud Collection API Tests
======================================================================
TEST 1: Create Collection
✅ Collection created successfully: AUA-6538

TEST 2: Get Collection Info
✅ Collection info retrieved successfully

TEST 3: Verify Password (should succeed)
✅ Password verified successfully

TEST 3: Verify Password (should fail)
✅ Password correctly rejected

TEST 4: Update Collection Alias
✅ Alias updated successfully: test-ml-conference

TEST 5: Verify by Alias
✅ Verification by alias successful

TEST 6: Update Collection Password
✅ Password updated successfully

TEST 7: Start Talk in Collection
✅ Talk created successfully

All Tests Completed!
======================================================================
✅ Created Collection: AUA-6538
✅ Set Alias: test-ml-conference
✅ Created Talk: 550e8400-e29b-41d4-a716-446655440000

You can now test the desktop client with:
  Collection ID/Alias: test-ml-conference or AUA-6538
  Password: new_password_456
```

**What this tests:**
- Collection creation with owner credentials
- Password verification (bcrypt)
- JWT token generation
- Alias management
- Password updates
- Talk creation

---

## Phase 2: Test Desktop Client (First-Time User)

### Launch Desktop Client

```bash
# Terminal 3: Start desktop client
python gui/main.py
```

Or if you have the GUI launcher:
```bash
python gui/windows/direct_talk_window.py
```

### First-Time Experience

1. **First Collection Dialog appears** (automatically)
   - You should see: "Welcome to SeenSlide - Create Your First Collection"

2. **Fill in collection details:**
   - Collection Name: `My First Collection`
   - Username: `user@example.com`
   - Password: (optional) `my_password_123`
   - Check "Set password" if testing multi-device

3. **Click "Create Collection"**
   - Collection created in cloud
   - Local registry updated (~/.config/seenslide/collections.yaml)
   - Credentials stored in keyring

4. **Direct Talk Window opens**
   - Cloud Collection ID displayed
   - Talk title: `Test Talk 1`
   - Click "Start Talk"

5. **Verify cloud session:**
   - Check admin server logs
   - Collection should NOT create new session (reuses existing)
   - Talk should start successfully

**What this tests:**
- First-time user onboarding
- Collection registry creation
- Credential storage (keyring/encrypted file)
- Cloud collection creation via API
- Reusing existing cloud collection ID

---

## Phase 3: Test Collection Manager

### Open Collection Manager

From Direct Talk Window:
- Menu → Collections → Manage Collections

Or run directly:
```bash
python -c "from PyQt5.QtWidgets import QApplication; from gui.windows.collection_manager_window import CollectionManagerWindow; import sys; app = QApplication(sys.argv); w = CollectionManagerWindow(); w.show(); sys.exit(app.exec_())"
```

### View Collections

You should see:
```
Your Collections:
------------------------------------------------------------
My First Collection
   ID: CLT-ABC-123  •  👤 Owner  •  ✅ CURRENT
```

### Test Collection Settings

1. **Click "Collection Settings"**
   - Collection info displayed
   - Sharing settings (owner only)

2. **Set an Alias:**
   - Alias: `my-first-collection`
   - Click "Save Changes"
   - Verify cloud API call succeeds

3. **Change Password:**
   - Check "Set/Change password"
   - New Password: `new_password_456`
   - Confirm Password: `new_password_456`
   - Click "Save Changes"

4. **Copy Collection ID:**
   - Click "Copy Collection ID to Clipboard"
   - Paste to verify: `my-first-collection` or `CLT-ABC-123`

**What this tests:**
- Collection listing from registry
- Collection settings dialog
- Alias update via cloud API
- Password update via cloud API
- Local registry synchronization

---

## Phase 4: Test Multi-Device Access (Join Collection)

### Simulate Second Device

For testing, we'll "join" the collection we just created as if from another device.

1. **Delete local collection** (simulates fresh device):
   ```bash
   # Backup first
   cp ~/.config/seenslide/collections.yaml ~/.config/seenslide/collections.yaml.bak

   # Remove the collection from registry
   # Edit collections.yaml and remove the collection entry
   # OR delete the file entirely to simulate fresh install
   rm ~/.config/seenslide/collections.yaml
   ```

2. **Restart Desktop Client:**
   ```bash
   python gui/main.py
   ```

3. **First Collection Dialog appears again**
   - This time, click "Cancel" or close the dialog

4. **Open Collection Manager:**
   - Click "Join Existing Collection"

5. **Enter Collection Details:**
   - Collection ID/Alias: `my-first-collection` (or the actual ID)
   - Password: `new_password_456` (the updated password)
   - Click "Join"

6. **Verify Join Success:**
   - Progress dialog: "Verifying collection password..."
   - Success message: "Successfully joined collection: My First Collection"
   - Collection appears in manager as "👥 Contributor"

7. **Restore backup:**
   ```bash
   mv ~/.config/seenslide/collections.yaml.bak ~/.config/seenslide/collections.yaml
   ```

**What this tests:**
- Password verification via cloud API
- Session token retrieval
- Adding collection as contributor
- Credential storage for joined collections
- Multi-device workflow

---

## Phase 5: Test Collection Switching

### Create Second Collection

1. **Collection Manager → "Create New Collection"**
   - Note: This button currently shows "Coming Soon" message
   - **Alternative:** Reset and create new via First Collection Dialog

2. **OR: Use First Collection Dialog**
   - Delete collections.yaml
   - Restart app
   - Create new collection: `My Second Collection`

3. **Open Collection Manager**
   - Should now see two collections

### Switch Between Collections

1. **Select a collection** (not current)

2. **Click "Switch to Collection"**
   - Confirmation dialog appears
   - "Please restart the app for the change to take effect"

3. **Restart the app:**
   - New current collection should be loaded
   - Cloud collection ID reused (no new session created)

**What this tests:**
- Multiple collection support
- Current collection tracking
- Collection switching
- Persistent cloud session reuse

---

## Phase 6: End-to-End Workflow

### Complete User Journey

1. **Day 1 - Create Collection (Device A):**
   - Launch app → First Collection Dialog
   - Create: "Conference 2026" with password
   - Start talk: "Opening Keynote"
   - Capture slides
   - Stop talk

2. **Day 2 - Join from Device B:**
   - Launch app on different machine
   - Join collection: "conference-2026" + password
   - Verify previous talk visible
   - Start new talk: "Session 1"
   - Capture slides

3. **Day 3 - Share with Collaborator:**
   - Update alias to something memorable
   - Share: Alias + Password
   - Collaborator joins as contributor
   - Adds new talk: "Guest Speaker"

4. **Day 4 - Owner Management:**
   - Owner can delete any talk
   - Contributor can only add talks
   - Owner changes password
   - Old password stops working

**What this tests:**
- Complete collection lifecycle
- Multi-device collaboration
- Permission system (owner vs contributor)
- Cloud synchronization
- Password management

---

## Verification Checklist

### Backend API ✓
- [x] Collection creation with unique ID
- [x] Password hashing (bcrypt)
- [x] Password verification (correct & incorrect)
- [x] JWT token generation
- [x] Alias assignment and lookup
- [x] Password updates
- [x] Talk creation in collection

### Desktop Client ✓
- [x] First-time user dialog
- [x] Collection registry creation
- [x] Credential storage (keyring/fallback)
- [x] Cloud session reuse (no duplicates)
- [x] Collection manager UI
- [x] Join collection workflow
- [x] Collection settings dialog
- [x] Alias and password updates

### Integration ✓
- [x] Cloud API calls from desktop
- [x] Local registry sync with cloud
- [x] Multi-device access via password
- [x] Session token storage and reuse
- [x] Owner vs contributor permissions

### Known Issues / TODO
- [ ] Create Collection from manager (shows "Coming Soon")
- [ ] Delete collection from cloud (only local delete)
- [ ] Slide upload via cloud API (placeholder)
- [ ] Token invalidation on password change
- [ ] Database persistence (in-memory only)
- [ ] Rate limiting on password verification

---

## Debugging Tips

### Check Collections Registry
```bash
cat ~/.config/seenslide/collections.yaml
```

Expected format:
```yaml
collections:
  CLT-ABC-123:
    collection_id: CLT-ABC-123
    cloud_collection_id: AUA-6538
    name: My First Collection
    owner_username: user@example.com
    is_owner: true
    access_level: owner
    created_at: '2026-01-05T10:00:00Z'
    alias: my-first-collection
    has_password: true
current_collection: CLT-ABC-123
```

### Check Stored Credentials
```bash
# If using keyring
python -c "import keyring; print(keyring.get_password('seenslide_collection', 'AUA-6538'))"

# If using encrypted fallback
ls -la ~/.config/seenslide/credentials/
```

### Check Cloud API
```bash
# Test direct API call
curl http://localhost:8081/api/cloud/session/AUA-6538

# Expected response
{
  "session_id": "AUA-6538",
  "name": "My First Collection",
  "has_password": true,
  ...
}
```

### Check Admin Server Logs
```bash
# In terminal where admin server is running
# Look for:
# - "Created collection: AUA-6538"
# - "Password verified for collection: AUA-6538"
# - "Updated alias for AUA-6538: ..."
# - "Updated password for collection: AUA-6538"
```

---

## Common Issues

### Issue: "Collection not found" when joining
**Cause:** Admin server restarted (in-memory storage lost)
**Fix:** Run `test_cloud_api.py` again to recreate test collection

### Issue: Password verification fails
**Cause:** Password was changed in test, or using wrong password
**Fix:** Use `new_password_456` if you ran full test suite

### Issue: Alias already in use
**Cause:** Previous test run didn't clean up
**Fix:** Use different alias or restart admin server

### Issue: Keyring not available
**Expected:** Falls back to encrypted file storage automatically
**Location:** `~/.config/seenslide/credentials/`

### Issue: First Collection Dialog doesn't appear
**Cause:** Collections already exist
**Fix:** Delete `~/.config/seenslide/collections.yaml` to reset

---

## Next Steps

After successful testing:

1. **Production Database:**
   - Replace in-memory storage with SQLite/PostgreSQL
   - Add database migrations

2. **Enhanced Security:**
   - Load JWT secret from environment
   - Add rate limiting
   - Implement HTTPS

3. **Additional Features:**
   - Email-based password reset
   - Collection deletion from cloud
   - Slide upload via API
   - Real-time collaboration

4. **Testing:**
   - Add unit tests
   - Add integration tests with database
   - Add load testing

---

## Success Criteria

You've successfully tested the collection system when:

✅ Backend tests pass (all 7 endpoints)
✅ First collection created from desktop
✅ Collection appears in manager
✅ Alias and password can be updated
✅ Can "join" collection with ID + password
✅ Multiple collections can exist
✅ Can switch between collections
✅ Cloud session ID is reused (not regenerated)
✅ Credentials stored securely

**Congratulations!** The collection management system is working end-to-end. 🎉
