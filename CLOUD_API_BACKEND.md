# SeenSlide Cloud Collection API - Backend Implementation

## Overview

This document describes the backend implementation of the SeenSlide Cloud Collection API. The API enables multi-device access, collection sharing, and collaborative talk management.

## Implementation Status

✅ **COMPLETE** - All core endpoints implemented and integrated

### Files Created/Modified

1. **`modules/admin/cloud_api.py`** (NEW)
   - FastAPI router with all collection management endpoints
   - JWT token generation/verification
   - Bcrypt password verification
   - In-memory storage (COLLECTIONS, ALIASES)

2. **`modules/admin/admin_server.py`** (MODIFIED)
   - Imported cloud API router
   - Mounted at `/api/cloud` prefix

3. **`test_cloud_api.py`** (NEW)
   - Comprehensive test suite for all endpoints
   - Automated validation of API spec compliance

## API Endpoints

### 1. Create Collection
**Endpoint:** `POST /api/cloud/session/create`

**Description:** Create a new collection with owner credentials.

**Request:**
```json
{
  "name": "ML Conference 2026",
  "presenter_name": "John Doe",
  "description": "Machine learning presentations",
  "is_private": false,
  "max_slides": 100,
  "admin_username": "john@example.com",
  "admin_password_hash": "$2b$12$..."
}
```

**Response:**
```json
{
  "session_id": "AUA-6538",
  "success": true
}
```

**Implementation:**
- Generates random collection ID (format: `XXX-NNNN`)
- Stores collection with owner credentials
- Returns collection ID for future reference

---

### 2. Verify Password
**Endpoint:** `POST /api/cloud/session/{id_or_alias}/verify`

**Description:** Verify password and get session token for authenticated access.

**Request:**
```json
{
  "password": "plain_text_password"
}
```

**Response (Success):**
```json
{
  "verified": true,
  "session_id": "AUA-6538",
  "owner_username": "john@example.com",
  "name": "ML Conference 2026",
  "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (Failed):**
```json
{
  "verified": false
}
```

**Implementation:**
- Supports both collection ID and alias
- Uses bcrypt for password verification
- Generates JWT token with 30-day expiry
- Token includes: collection_id, username, exp, iat

---

### 3. Get Collection Info
**Endpoint:** `GET /api/cloud/session/{id_or_alias}`

**Description:** Retrieve public collection metadata.

**Response:**
```json
{
  "session_id": "AUA-6538",
  "name": "ML Conference 2026",
  "description": "Machine learning presentations",
  "presenter_name": "John Doe",
  "created_at": "2026-01-05T10:00:00Z",
  "is_private": false,
  "has_password": true,
  "alias": "ml-conference-2026"
}
```

**Implementation:**
- No authentication required (public endpoint)
- Returns metadata only (no password hash)
- Supports lookup by ID or alias

---

### 4. Update Collection Alias
**Endpoint:** `POST /api/cloud/session/{session_id}/alias`

**Description:** Set or update user-friendly alias for easier sharing.

**Request:**
```json
{
  "alias": "ml-conference-2026"
}
```

**To remove alias:**
```json
{
  "alias": null
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "AUA-6538",
  "alias": "ml-conference-2026"
}
```

**Implementation:**
- Validates alias format (alphanumeric, hyphens, underscores)
- Enforces length constraints (3-50 characters)
- Ensures alias uniqueness across all collections
- Updates both collection data and alias mapping

---

### 5. Update Collection Password
**Endpoint:** `POST /api/cloud/session/{session_id}/password`

**Description:** Update collection password (owner only).

**Request:**
```json
{
  "admin_username": "john@example.com",
  "new_password_hash": "$2b$12$newHash..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Password updated successfully"
}
```

**Implementation:**
- Verifies requesting user is collection owner
- Updates password hash
- **Note:** Should invalidate all session tokens (not yet implemented)

---

### 6. Start Talk in Collection
**Endpoint:** `POST /api/cloud/session/{session_id}/start-talk`

**Description:** Create a new talk within a collection.

**Request:**
```json
{
  "title": "Introduction to Deep Learning",
  "description": "Basics of neural networks"
}
```

**Response:**
```json
{
  "success": true,
  "talk": {
    "talk_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Introduction to Deep Learning",
    "description": "Basics of neural networks",
    "session_id": "AUA-6538",
    "created_at": "2026-01-05T14:30:00Z",
    "slide_count": 0
  }
}
```

**Implementation:**
- Generates UUID for talk
- Associates talk with collection
- Returns complete talk object

---

### 7. Upload Slide
**Endpoint:** `POST /api/cloud/session/{session_id}/upload-slide?slide_number={n}`

**Description:** Upload slide image to collection.

**Request:** Multipart form-data with image file

**Response:**
```json
{
  "success": true,
  "slide_id": "slide-1",
  "slide_number": 1
}
```

**Implementation:**
- **Status:** Placeholder (not yet fully implemented)
- Requires file upload handling
- Should store slide image and create database record

---

## Security Features

### Password Storage
- **Algorithm:** bcrypt with default cost factor (12)
- **Storage:** Only hashes stored, never plain passwords
- **Verification:** Constant-time comparison via bcrypt.checkpw()

### Session Tokens (JWT)
- **Algorithm:** HMAC-SHA256 (HS256)
- **Expiry:** 30 days from issuance
- **Claims:**
  - `sub`: Collection ID
  - `username`: Owner username
  - `exp`: Expiration timestamp
  - `iat`: Issued at timestamp
  - `device_fingerprint`: (Optional) Device identifier

### Secret Key
- **Current:** Generated at runtime (random 32 bytes)
- **Production:** Should load from environment variable
- **Note:** Restart invalidates all tokens (acceptable for prototype)

---

## Data Storage

### In-Memory Storage (Current)

**Collections Dictionary:**
```python
COLLECTIONS = {
    "AUA-6538": {
        "session_id": "AUA-6538",
        "name": "ML Conference 2026",
        "description": "...",
        "presenter_name": "John Doe",
        "created_at": "2026-01-05T10:00:00Z",
        "updated_at": "2026-01-05T10:00:00Z",
        "is_private": false,
        "has_password": true,
        "alias": "ml-conference-2026",
        "owner_username": "john@example.com",
        "admin_password_hash": "$2b$12$...",
        "max_slides": 100,
        "talks": [...]
    }
}
```

**Aliases Dictionary:**
```python
ALIASES = {
    "ml-conference-2026": "AUA-6538"
}
```

### Production Storage (TODO)

For production deployment, replace in-memory storage with:
- **Database:** PostgreSQL or SQLite
- **Schema:**
  ```sql
  CREATE TABLE collections (
      session_id VARCHAR(20) PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      description TEXT,
      presenter_name VARCHAR(255),
      created_at TIMESTAMP NOT NULL,
      updated_at TIMESTAMP NOT NULL,
      is_private BOOLEAN DEFAULT FALSE,
      has_password BOOLEAN DEFAULT FALSE,
      alias VARCHAR(50) UNIQUE,
      owner_username VARCHAR(255) NOT NULL,
      admin_password_hash VARCHAR(255) NOT NULL,
      max_slides INTEGER DEFAULT 100
  );

  CREATE TABLE talks (
      talk_id UUID PRIMARY KEY,
      session_id VARCHAR(20) REFERENCES collections(session_id),
      title VARCHAR(255) NOT NULL,
      description TEXT,
      created_at TIMESTAMP NOT NULL,
      slide_count INTEGER DEFAULT 0
  );
  ```

---

## Testing

### Automated Test Suite

**Run tests:**
```bash
# Start admin server (Terminal 1)
python seenslide.py admin --port 8081

# Run tests (Terminal 2)
python test_cloud_api.py
```

**Test Coverage:**
- ✅ Create collection with owner credentials
- ✅ Get collection info (public endpoint)
- ✅ Verify password (correct & incorrect)
- ✅ Update collection alias
- ✅ Verify by alias
- ✅ Update password
- ✅ Verify new password works & old fails
- ✅ Start talk in collection

### Manual Testing with Desktop Client

1. **Start admin server:**
   ```bash
   python seenslide.py admin --port 8081
   ```

2. **Run test_cloud_api.py** to create a test collection

3. **Join collection from desktop:**
   - Open Collection Manager
   - Click "Join Existing Collection"
   - Enter: `test-ml-conference` (alias) or collection ID
   - Password: `new_password_456` (after password update test)

---

## Integration with Desktop Client

The desktop client (`gui/` modules) integrates with this API via `CloudStorageProvider`:

### Collection Creation (Phase 2)
```python
# In direct_talk_window.py
cloud.start_session(
    session_id="",
    session_name=collection_name,
    admin_username=username,
    admin_password_hash=password_hash
)
```

### Collection Verification (Phase 4)
```python
# In collection_manager_window.py
result = cloud.verify_collection_password(
    collection_id_or_alias,
    password
)
# Returns: {collection_id, owner_username, session_token, name}
```

### Alias Management (Phase 4)
```python
# In collection_settings_dialog.py
success = cloud.update_collection_alias(
    collection_id,
    alias
)
```

### Password Update (Phase 4)
```python
# In collection_settings_dialog.py
success = cloud.update_collection_password(
    collection_id,
    admin_username,
    new_password_hash
)
```

---

## Known Limitations

### 1. In-Memory Storage
- **Issue:** Data lost on server restart
- **Impact:** All collections and talks disappear
- **Mitigation:** Add database persistence layer

### 2. Secret Key Rotation
- **Issue:** JWT secret generated at runtime
- **Impact:** Server restart invalidates all tokens
- **Mitigation:** Load secret from environment variable

### 3. Token Invalidation
- **Issue:** Password change doesn't invalidate old tokens
- **Impact:** Old tokens still work for 30 days
- **Mitigation:** Add token blacklist or version tracking

### 4. File Upload
- **Issue:** Slide upload endpoint is placeholder
- **Impact:** Can't upload slides via API yet
- **Mitigation:** Implement multipart/form-data handling

### 5. Rate Limiting
- **Issue:** No rate limiting on password verification
- **Impact:** Vulnerable to brute force attacks
- **Mitigation:** Add rate limiting middleware

### 6. HTTPS
- **Issue:** Development server uses HTTP
- **Impact:** Passwords transmitted in plain text (hashed but not encrypted)
- **Mitigation:** Use HTTPS in production with proper certificates

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Replace in-memory storage with database
- [ ] Load JWT secret from environment variable
- [ ] Implement token invalidation on password change
- [ ] Add rate limiting (5 attempts/15min for password verification)
- [ ] Enable HTTPS with valid certificates
- [ ] Add input sanitization and validation
- [ ] Implement proper logging and monitoring
- [ ] Add backup and recovery procedures
- [ ] Set up database migrations
- [ ] Configure CORS for production domain
- [ ] Add health check endpoint
- [ ] Implement graceful shutdown

---

## API Documentation

The API is automatically documented using FastAPI's built-in Swagger UI:

**Access Swagger docs:**
```
http://localhost:8081/docs
```

This provides:
- Interactive API testing
- Request/response schemas
- Example payloads
- Authentication requirements

---

## Next Steps

1. **Database Integration**
   - Create SQLite schema for collections and talks
   - Migrate in-memory storage to database
   - Add database migrations support

2. **Enhanced Security**
   - Add rate limiting middleware
   - Implement token refresh mechanism
   - Add device fingerprinting validation
   - Set up HTTPS for production

3. **File Upload**
   - Implement multipart/form-data handling
   - Add file size limits and validation
   - Store slides in cloud storage (S3, etc.)

4. **Testing**
   - Add unit tests for all endpoints
   - Add integration tests with database
   - Add load testing for concurrent access

5. **Monitoring**
   - Add request logging
   - Set up error tracking (Sentry, etc.)
   - Add performance metrics
   - Create admin dashboard for monitoring

---

## Contact

For questions or issues with the cloud API implementation:
- Check `CLOUD_API_SPEC.md` for API specification
- Review `test_cloud_api.py` for usage examples
- See `/docs` endpoint for interactive documentation
