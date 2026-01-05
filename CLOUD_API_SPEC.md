# SeenSlide Cloud API Specification

## Overview

This document specifies the cloud API endpoints required for SeenSlide's collection management system. These endpoints enable cross-device access, collection sharing, and multi-user collaboration.

## Base URL

```
https://seenslide.com/api/cloud
```

## Authentication

Most endpoints use Bearer token authentication:

```
Authorization: Bearer {session_token}
```

Some endpoints (like password verification) don't require authentication.

---

## Endpoints

### 1. Create Collection (Session)

**Endpoint:** `POST /session/create`

**Description:** Creates a new collection with owner credentials.

**Headers:**
```
Authorization: Bearer {session_token}
Content-Type: application/json
```

**Request Body:**
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

**Response (200 OK):**
```json
{
  "session_id": "AUA-6538",
  "success": true
}
```

**Notes:**
- `admin_username` and `admin_password_hash` are REQUIRED for ownership
- `password_hash` must be bcrypt with cost factor 12
- `session_id` is a short random ID (e.g., AUA-6538, IRA-9705)

---

### 2. Verify Collection Password

**Endpoint:** `POST /session/{id_or_alias}/verify`

**Description:** Verifies password and grants access to collection. Used for joining collections from other devices or users.

**Headers:**
```
Content-Type: application/json
```

**URL Parameters:**
- `id_or_alias`: Collection ID (e.g., AUA-6538) or alias (e.g., ml-conference-2026)

**Request Body:**
```json
{
  "password": "plain_text_password"
}
```

**Response (200 OK):**
```json
{
  "verified": true,
  "session_id": "AUA-6538",
  "owner_username": "john@example.com",
  "name": "ML Conference 2026",
  "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (401 Unauthorized):**
```json
{
  "verified": false,
  "message": "Invalid password"
}
```

**Response (404 Not Found):**
```json
{
  "detail": "Collection not found"
}
```

**Notes:**
- Server must verify password using bcrypt
- Returns JWT `session_token` for authenticated API calls
- Token should have 30-day expiry
- Token should include device fingerprint in claims

---

### 3. Get Collection Info

**Endpoint:** `GET /session/{id_or_alias}`

**Description:** Retrieves collection metadata (public information only).

**Headers:**
```
Content-Type: application/json
```

**URL Parameters:**
- `id_or_alias`: Collection ID or alias

**Response (200 OK):**
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

**Response (404 Not Found):**
```json
{
  "detail": "Collection not found"
}
```

---

### 4. Update Collection Alias

**Endpoint:** `POST /session/{session_id}/alias`

**Description:** Sets or updates the collection alias for easier sharing.

**Headers:**
```
Content-Type: application/json
```

**URL Parameters:**
- `session_id`: Collection ID (not alias)

**Request Body:**
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

**Response (200 OK):**
```json
{
  "success": true,
  "session_id": "AUA-6538",
  "alias": "ml-conference-2026"
}
```

**Response (409 Conflict):**
```json
{
  "success": false,
  "message": "Alias already in use"
}
```

**Notes:**
- Alias must be unique across all collections
- Alias validation: alphanumeric, hyphens, underscores only
- Length: 3-50 characters

---

### 5. Update Collection Password

**Endpoint:** `POST /session/{session_id}/password`

**Description:** Updates the collection password for sharing/multi-device access.

**Headers:**
```
Content-Type: application/json
```

**URL Parameters:**
- `session_id`: Collection ID

**Request Body:**
```json
{
  "admin_username": "john@example.com",
  "new_password_hash": "$2b$12$newHash..."
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Password updated successfully"
}
```

**Response (403 Forbidden):**
```json
{
  "success": false,
  "message": "Only owner can update password"
}
```

**Notes:**
- Must verify `admin_username` matches collection owner
- `new_password_hash` must be bcrypt
- Invalidates all existing session tokens (force re-auth)

---

### 6. Start Talk (Create Talk in Collection)

**Endpoint:** `POST /session/{session_id}/start-talk`

**Description:** Creates a new talk within a collection.

**Headers:**
```
Content-Type: application/json
```

**URL Parameters:**
- `session_id`: Collection ID

**Request Body:**
```json
{
  "title": "Introduction to Deep Learning",
  "description": "Basics of neural networks"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "talk": {
    "talk_id": "generated-uuid",
    "title": "Introduction to Deep Learning",
    "session_id": "AUA-6538",
    "created_at": "2026-01-05T14:30:00Z"
  }
}
```

**Notes:**
- Current implementation doesn't send presenter_name (should we add it?)
- Talk belongs to collection, multiple talks per collection

---

### 7. Upload Slide

**Endpoint:** `POST /session/{session_id}/upload-slide?slide_number={n}`

**Description:** Uploads a slide image to a collection.

**Headers:**
```
Authorization: Bearer {session_token}
```

**URL Parameters:**
- `session_id`: Collection ID
- `slide_number`: Sequence number (1, 2, 3...)

**Request Body:**
```
multipart/form-data
file: <binary image data>
```

**Response (200 OK):**
```json
{
  "success": true,
  "slide_id": "generated-uuid",
  "slide_number": 1
}
```

---

## Data Models

### Collection (Session)

```typescript
interface Collection {
  session_id: string;           // Short ID (AUA-6538)
  name: string;                 // Display name
  description?: string;
  presenter_name?: string;
  created_at: string;           // ISO 8601
  updated_at: string;
  is_private: boolean;
  has_password: boolean;
  alias?: string;               // User-friendly alias
  owner_username: string;       // Owner email/username
  admin_password_hash: string;  // Bcrypt hash (NOT returned in API)
}
```

### Talk

```typescript
interface Talk {
  talk_id: string;              // UUID
  session_id: string;           // Parent collection
  title: string;
  description?: string;
  presenter_name?: string;
  created_at: string;
  slide_count: number;
}
```

### Session Token (JWT)

```typescript
interface SessionToken {
  sub: string;                  // session_id
  username: string;             // owner_username
  exp: number;                  // Expiry timestamp (30 days)
  iat: number;                  // Issued at
  device_fingerprint?: string;  // Device ID for security
}
```

---

## Security Considerations

### Password Storage

- **ALWAYS** use bcrypt for password hashing
- Cost factor: 12
- Never return password hashes in API responses
- Never log passwords (even hashed)

### Session Tokens

- Use JWT with HMAC-SHA256
- 30-day expiry (refresh before 7 days remaining)
- Include device fingerprint for added security
- Invalidate all tokens on password change

### Rate Limiting

Recommended limits:
- Password verification: 5 attempts per 15 minutes per IP
- Collection creation: 10 per hour per user
- Slide upload: 100 per minute per collection

### HTTPS Only

All endpoints MUST use HTTPS in production.

---

## Error Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Collection verified |
| 400 | Bad Request | Invalid alias format |
| 401 | Unauthorized | Invalid password |
| 403 | Forbidden | Not collection owner |
| 404 | Not Found | Collection doesn't exist |
| 409 | Conflict | Alias already taken |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Database failure |

---

## Example Workflows

### Workflow 1: First-Time User (Single Device)

```
1. Desktop app opens
2. No collections exist locally
3. User enters collection name + username (password optional)
4. POST /session/create
   {
     "name": "My Talks 2026",
     "admin_username": "user@example.com",
     "admin_password_hash": null  // No password for single device
   }
5. Receive: session_id = "AUA-6538"
6. Save to ~/.config/seenslide/collections.yaml
7. Set as current collection
8. User starts talks → all go into AUA-6538
```

### Workflow 2: Multi-Device Access (Same User)

**Device A (First time):**
```
1. Create collection with password
   POST /session/create
   {
     "admin_username": "user@example.com",
     "admin_password_hash": "$2b$12$..."
   }
2. Save session_id = "AUA-6538"
```

**Device B (Later):**
```
1. User wants to access same collection
2. Open Collection Manager → "Join Existing Collection"
3. Enter: AUA-6538 + password
4. POST /session/AUA-6538/verify
   { "password": "plain_password" }
5. Receive: session_token + collection info
6. Save to local registry
7. Now both devices use same collection!
```

### Workflow 3: Share Collection (Multi-User)

**Owner:**
```
1. Create collection with password
2. Set alias for easy sharing:
   POST /session/AUA-6538/alias
   { "alias": "ml-conference-2026" }
3. Share with collaborators:
   - Collection ID: ml-conference-2026
   - Password: secret123
```

**Contributor:**
```
1. Receives: ml-conference-2026 + password
2. Join Collection dialog
3. POST /session/ml-conference-2026/verify
   { "password": "secret123" }
4. Added as contributor
5. Can add talks, cannot delete collection or change password
```

---

## Testing Checklist

### Collection Management
- [ ] Create collection with username + password
- [ ] Create collection without password (single device)
- [ ] Verify correct password
- [ ] Reject incorrect password
- [ ] Handle non-existent collection ID
- [ ] Handle invalid alias format

### Cross-Device Access
- [ ] Join collection from Device B
- [ ] Both devices can add talks to same collection
- [ ] Session token persists across app restarts
- [ ] Token refresh works before expiry

### Alias Management
- [ ] Set alias on new collection
- [ ] Update existing alias
- [ ] Remove alias (set to null)
- [ ] Reject duplicate aliases
- [ ] Join by alias instead of ID

### Password Management
- [ ] Update collection password
- [ ] Old password stops working
- [ ] New password grants access
- [ ] Only owner can change password

---

## Implementation Status

### Desktop App (Complete)
- ✅ Collection registry with local storage
- ✅ Password hashing (bcrypt)
- ✅ Session token storage (keyring/fallback)
- ✅ Join collection dialog
- ✅ Collection settings dialog
- ✅ Cloud API client methods

### Cloud Backend (Pending)
- ⏳ Implement endpoints listed above
- ⏳ Database schema for collections
- ⏳ JWT token generation/validation
- ⏳ Password verification with bcrypt
- ⏳ Alias uniqueness constraints

---

## Questions for Backend Team

1. **Database Schema**: Do we need to add any new tables/columns for:
   - Collection aliases (unique constraint)
   - Owner username tracking
   - Session tokens (or just stateless JWT?)

2. **Password Reset**: Should we implement email-based password reset?
   - Endpoint: POST /session/reset-password
   - Requires email integration

3. **Session Token Format**: Preferences for JWT claims?
   - Current proposal: sub, username, exp, iat, device_fingerprint

4. **Migration**: How to handle existing sessions without admin credentials?
   - Should we backfill with a default username?
   - Or require users to "claim" their sessions?

5. **Rate Limiting**: Which rate limiting strategy to use?
   - IP-based?
   - User-based (after auth)?
   - Collection-based?

---

## Contact

For questions or clarifications about this API specification, please create an issue in the GitHub repository.
