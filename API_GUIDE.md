# Telegram Scraper API v2.0 - Complete Guide

## 🎯 Overview

This API provides session management and source creation for Telegram channel scraping with two distinct workflows:
- **Private Channels**: Use stored user sessions
- **Public Channels**: Use shared session or bot token

---

## 📋 API Endpoints

### Session Management

#### 1. Create Session
```http
POST /sessions/
```

**Purpose**: Upload and store a Telegram user session for accessing private channels

**Request (Form Data)**:
```json
{
  "name": "My Personal Account",
  "phone_number": "+1234567890",
  "api_id": 12345678,
  "api_hash": "your_api_hash_here",
  "session_string": "telethon_string_session_data"
}
```

**Response**:
```json
{
  "id": "uuid-here",
  "name": "My Personal Account",
  "phone_number": "+1234567890",
  "api_id": 12345678,
  "is_active": "active",
  "created_at": "2025-10-30T12:00:00Z"
}
```

---

#### 2. List All Sessions
```http
GET /sessions/
```

**Response**:
```json
[
  {
    "id": "uuid-1",
    "name": "Account 1",
    "phone_number": "+1234567890",
    "api_id": 12345678,
    "is_active": "active",
    "created_at": "2025-10-30T12:00:00Z"
  }
]
```

---

#### 3. Get Session Details
```http
GET /sessions/{session_id}
```

**Response**: Same as create response

---

#### 4. Get Session Channels ⭐
```http
GET /sessions/{session_id}/channels
```

**Purpose**: Fetch all channels accessible by this session

**Response**:
```json
[
  {
    "id": 1234567890,
    "username": "techNews",
    "title": "Tech News Channel",
    "participants_count": 50000,
    "is_broadcast": true,
    "is_megagroup": false,
    "is_private": false,
    "access_hash": 1234567890123456789,
    "description": "Latest tech news"
  },
  {
    "id": 9876543210,
    "username": null,
    "title": "Private Group",
    "participants_count": 150,
    "is_broadcast": false,
    "is_megagroup": true,
    "is_private": true,
    "access_hash": 9876543210987654321,
    "description": null
  }
]
```

---

#### 5. Test Session
```http
POST /sessions/{session_id}/test
```

**Purpose**: Verify if session is still valid

**Response**:
```json
{
  "session_id": "uuid-here",
  "is_valid": true,
  "status": "active"
}
```

---

#### 6. Update Session
```http
PUT /sessions/{session_id}
```

**Request**:
```json
{
  "name": "Updated Name",
  "is_active": "inactive"
}
```

---

#### 7. Delete Session
```http
DELETE /sessions/{session_id}
```

**Response**:
```json
{
  "message": "Session deleted successfully",
  "id": "uuid-here"
}
```

**Note**: Cannot delete if sources are using this session

---

### Source Management

#### 8. Create Private Channel Source
```http
POST /sources/private
```

**Purpose**: Create a source for a private channel using an existing session

**Workflow**:
1. Select session → `GET /sessions/`
2. Get channels → `GET /sessions/{id}/channels`
3. Select channel from list
4. Create source with this endpoint

**Request**:
```json
{
  "name": "Tech News Private",
  "api_id": 12345678,
  "api_hash": "your_api_hash",
  "session_id": "uuid-of-session",
  "channel_id": 1234567890,
  "channel_title": "Tech News Channel",
  "file_types": ["pdf", "zip", "jpg"],
  "target": "LOCAL",
  "target_path": "/downloads/tech",
  "schedule": "0 */6 * * *"
}
```

**Response**:
```json
{
  "id": "source-uuid",
  "name": "Tech News Private",
  "access_level": "private",
  "identifier": "1234567890",
  "channel_title": "Tech News Channel",
  "file_types": ["pdf", "zip", "jpg"],
  "target": "LOCAL",
  "target_path": "/downloads/tech",
  "schedule": "0 */6 * * *",
  "is_active": "active",
  "created_at": "2025-10-30T12:00:00Z",
  "total_messages_scraped": 0,
  "total_files_downloaded": 0
}
```

---

#### 9. Create Public Channel Source
```http
POST /sources/public
```

**Purpose**: Create a source for a public channel

**Request**:
```json
{
  "name": "Public Tech Channel",
  "api_id": 12345678,
  "api_hash": "your_api_hash",
  "channel_username": "@technews",
  "bot_token": "optional_bot_token",
  "file_types": ["pdf"],
  "target": "NAS",
  "target_path": "/nas/tech",
  "schedule": "0 0 * * *"
}
```

**Response**: Same structure as private source

---

#### 10. List All Sources
```http
GET /sources/
```

---

#### 11. Get Source Details
```http
GET /sources/{source_id}
```

---

#### 12. Update Source
```http
PUT /sources/{source_id}
```

**Request**:
```json
{
  "name": "Updated Name",
  "schedule": "0 */12 * * *",
  "file_types": ["pdf", "docx"],
  "is_active": "inactive"
}
```

---

#### 13. Delete Source
```http
DELETE /sources/{source_id}
```

Automatically deletes associated Prefect deployment

---

#### 14. Trigger Source Manually
```http
POST /sources/{source_id}/trigger
```

**Purpose**: Immediately run scraper for this source

**Response**:
```json
{
  "message": "Triggered flow for source uuid-here",
  "result": {...}
}
```

---

## 🔄 Complete Workflows

### Workflow A: Private Channel

```bash
# Step 1: Create session
POST /sessions/
{
  "name": "My Account",
  "phone_number": "+1234567890",
  "api_id": 12345678,
  "api_hash": "abc123",
  "session_string": "session_data"
}
# Response: {"id": "session-uuid-123", ...}

# Step 2: Get channels from this session
GET /sessions/session-uuid-123/channels
# Response: [
#   {"id": 1001, "title": "Private Group", "is_private": true, ...},
#   {"id": 1002, "title": "Another Channel", ...}
# ]

# Step 3: Create source for selected channel
POST /sources/private
{
  "name": "Private Group Scraper",
  "api_id": 12345678,
  "api_hash": "abc123",
  "session_id": "session-uuid-123",
  "channel_id": 1001,
  "channel_title": "Private Group",
  "file_types": ["pdf"],
  "target": "LOCAL",
  "schedule": "0 */6 * * *"
}
# Response: {"id": "source-uuid-456", ...}

# Step 4: (Optional) Manually trigger
POST /sources/source-uuid-456/trigger
```

---

### Workflow B: Public Channel

```bash
# Step 1: Create source directly
POST /sources/public
{
  "name": "Public Tech News",
  "api_id": 12345678,
  "api_hash": "abc123",
  "channel_username": "@technews",
  "file_types": ["pdf", "zip"],
  "target": "S3",
  "schedule": "0 0 * * *"
}
# Response: {"id": "source-uuid-789", ...}

# Step 2: (Optional) Manually trigger
POST /sources/source-uuid-789/trigger
```

---

## 🔐 Authentication & Security

- All `api_hash` values are encrypted before storage
- All `session_string` values are encrypted
- Bot tokens (if provided) are encrypted
- Session validation on upload
- Cannot delete sessions in use by sources

---

## 📊 Data Models

### Session
- `id`: UUID
- `name`: User-friendly name
- `phone_number`: Phone number (unique)
- `session_string`: Encrypted Telethon session
- `api_id`: Telegram API ID
- `api_hash`: Encrypted API hash
- `is_active`: "active" | "expired" | "revoked"

### Source
- `id`: UUID
- `name`: Source name
- `api_id`: Encrypted API ID
- `api_hash`: Encrypted API hash
- `access_level`: "public" | "private"
- `identifier`: Channel username or ID
- `channel_title`: Display name
- `session_id`: FK to sessions (for private)
- `bot_token`: Encrypted token (for public, optional)
- `file_types`: Array of extensions
- `target`: "LOCAL" | "NAS" | "S3"
- `target_path`: Storage path
- `schedule`: Cron expression
- `is_active`: "active" | "inactive"
- Statistics fields...

---

## 🎨 Frontend Integration Example

```javascript
// 1. Get all sessions
const sessions = await fetch('/sessions/').then(r => r.json());

// 2. User selects a session
const selectedSession = sessions[0];

// 3. Get channels for that session
const channels = await fetch(`/sessions/${selectedSession.id}/channels`)
  .then(r => r.json());

// 4. Display channels to user (dropdown/list)
// User selects: channelId = 1234567890

// 5. Create source
await fetch('/sources/private', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    name: "My Scraper",
    api_id: 12345678,
    api_hash: "abc123",
    session_id: selectedSession.id,
    channel_id: 1234567890,
    channel_title: "Channel Name",
    file_types: ["pdf", "zip"],
    target: "LOCAL",
    schedule: "0 */6 * * *"
  })
});
```

---

## ✅ Testing

```bash
# Health check
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs

# Create session
curl -X POST http://localhost:8000/sessions/ \
  -F "name=Test Account" \
  -F "phone_number=+1234567890" \
  -F "api_id=12345678" \
  -F "api_hash=abcdef" \
  -F "session_string=session_data_here"

# Get channels
curl http://localhost:8000/sessions/{session-id}/channels

# Create source
curl -X POST http://localhost:8000/sources/private \
  -H "Content-Type: application/json" \
  -d '{...}'
```

---

## 🚀 Next Steps

1. Generate Telethon session string (see TELETHON_SETUP.md)
2. Create session via API
3. Fetch channels
4. Create sources
5. Monitor scraping in Prefect UI (http://localhost:4200)

---

## 📝 Notes

- **Session String**: Must be generated using Telethon library
- **API Credentials**: Get from https://my.telegram.org
- **Schedules**: Use cron expressions (e.g., `0 */6 * * *` = every 6 hours)
- **Targets**: LOCAL, NAS, S3 (implementation varies)
- **File Types**: Extensions without dot (e.g., `["pdf", "jpg"]`)
