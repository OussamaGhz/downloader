# Telegram Scraper Backend API Documentation

## Overview

This API provides endpoints for managing Telegram sessions and configuring scraping sources. The backend uses Prefect for workflow orchestration to scrape content from Telegram channels.

**Base URL**: `http://localhost:8000`

---

## Frontend Architecture

The frontend consists of **two separate pages**:

### 1. **Session Management Page** (`/sessions`)
- Manage Telegram authentication sessions
- Two authentication methods:
  - **Interactive OTP Flow**: Phone number → OTP → Password (if 2FA enabled)
  - **Session File Upload**: Upload pre-authenticated `.session` file
- View all saved sessions
- Delete sessions when no longer needed

### 2. **Sources Management Page** (`/sources`)
- Configure scraping sources (Telegram channels)
- Link sources to authenticated sessions (for private channels)
- View all configured sources
- Delete sources
- **Note**: Sources trigger Prefect flows automatically to scrape content

---

## Authentication Flow Logic

### Method 1: Interactive OTP Authentication (Multi-Step)

This is a **3-step process** for authenticating with Telegram:

```
Step 1: Send OTP          →  Step 2: Verify OTP/Password  →  Step 3: Finalize Session
(POST /sessions/send-otp)    (POST /sessions/verify-otp)      (POST /sessions/finalize)
```

#### Why Multi-Step?
- Telegram requires interactive authentication
- May need 2FA password after OTP
- Session is stored temporarily until finalized

#### Workflow Details:

**Step 1: Send OTP**
- User enters phone number and session name
- Backend creates temporary session
- Telegram sends OTP to user's phone
- Returns `temp_session_id` for next steps

**Step 2: Verify OTP (and Password if needed)**
- User enters OTP code
- If 2FA enabled: also enter password
- Backend verifies with Telegram
- Keeps temp session alive

**Step 3: Finalize Session**
- Backend saves permanent session to database
- Deletes temporary session
- Returns final session details

### Method 2: Upload Session File (Single Step)

```
Upload Session File
(POST /sessions/upload-file)
```

- User already has a `.session` file from Telethon
- Upload directly without OTP flow
- Instant authentication

---

## API Endpoints Reference

## 📱 Session Management Endpoints

### 1. Send OTP (Step 1)

**Endpoint**: `POST /sessions/send-otp`

**Description**: Initiates the OTP authentication flow by sending a verification code to the user's phone.

**Request Body**:
```json
{
  "phone_number": "+1234567890",
  "session_name": "my_telegram_session"
}
```

**Response** (200 OK):
```json
{
  "message": "OTP sent to +1234567890",
  "temp_session_id": "uuid-here",
  "phone_code_hash": "hash-value"
}
```

**Frontend Actions**:
- Store `temp_session_id` for subsequent requests
- Show OTP input form
- Display message to user: "Check your Telegram app for the verification code"

---

### 2. Verify OTP (Step 2)

**Endpoint**: `POST /sessions/verify-otp`

**Description**: Verifies the OTP code (and password if 2FA is enabled).

**Request Body**:
```json
{
  "temp_session_id": "uuid-from-step-1",
  "code": "12345"
}
```

**If 2FA is enabled**, also include:
```json
{
  "temp_session_id": "uuid-from-step-1",
  "code": "12345",
  "password": "my_2fa_password"
}
```

**Response** (200 OK):
```json
{
  "message": "Authentication successful. Ready to finalize.",
  "requires_password": false
}
```

**OR** (if 2FA required):
```json
{
  "message": "2FA password required",
  "requires_password": true
}
```

**Frontend Actions**:
- If `requires_password: true`: Show password input field, user re-submits with password
- If `requires_password: false`: Proceed to Step 3 (finalize)

---

### 3. Finalize Session (Step 3)

**Endpoint**: `POST /sessions/finalize`

**Description**: Saves the authenticated session permanently to the database.

**Request Body**:
```json
{
  "temp_session_id": "uuid-from-step-1"
}
```

**Response** (200 OK):
```json
{
  "id": 1,
  "session_name": "my_telegram_session",
  "phone_number": "+1234567890",
  "created_at": "2025-10-30T10:00:00Z"
}
```

**Frontend Actions**:
- Show success message: "Session saved successfully!"
- Clear form and temp session data
- Redirect to session list or allow creating another session

---

### 4. Upload Session File (Alternative Method)

**Endpoint**: `POST /sessions/upload-file`

**Description**: Upload a pre-authenticated Telethon `.session` file directly.

**Request**:
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `session_name`: string (e.g., "my_session")
  - `phone_number`: string (e.g., "+1234567890")
  - `session_file`: file upload (.session file)

**Example using fetch**:
```javascript
const formData = new FormData();
formData.append('session_name', 'my_session');
formData.append('phone_number', '+1234567890');
formData.append('session_file', fileInput.files[0]);

fetch('http://localhost:8000/sessions/upload-file', {
  method: 'POST',
  body: formData
});
```

**Response** (200 OK):
```json
{
  "id": 2,
  "session_name": "my_session",
  "phone_number": "+1234567890",
  "created_at": "2025-10-30T10:05:00Z"
}
```

**Frontend Actions**:
- Show file upload input
- Show success message after upload
- Refresh session list

---

### 5. List All Sessions

**Endpoint**: `GET /sessions/`

**Description**: Retrieve all saved Telegram sessions.

**Response** (200 OK):
```json
[
  {
    "id": 1,
    "session_name": "my_telegram_session",
    "phone_number": "+1234567890",
    "created_at": "2025-10-30T10:00:00Z"
  },
  {
    "id": 2,
    "session_name": "another_session",
    "phone_number": "+9876543210",
    "created_at": "2025-10-30T10:05:00Z"
  }
]
```

**Frontend Actions**:
- Display sessions in a table/list
- Show session name, phone number, creation date
- Provide delete button for each session

---

### 6. Get Session Channels

**Endpoint**: `GET /sessions/{session_id}/channels`

**Description**: Discover all channels and groups that this session has access to. This is useful for letting users browse and select channels to scrape.

**Path Parameters**:
- `session_id`: integer (e.g., 1)

**Response** (200 OK):
```json
[
  {
    "id": 1234567890,
    "username": "bbcnews",
    "title": "BBC News",
    "participants_count": 500000,
    "is_broadcast": true,
    "is_megagroup": false,
    "is_private": false,
    "access_hash": 1234567890123456789,
    "description": "Breaking news from BBC"
  },
  {
    "id": 9876543210,
    "username": null,
    "title": "Private VIP Group",
    "participants_count": 150,
    "is_broadcast": false,
    "is_megagroup": true,
    "is_private": true,
    "access_hash": 9876543210987654321,
    "description": "Exclusive VIP content"
  }
]
```

**Field Descriptions**:
- `id`: Telegram channel/group ID
- `username`: Channel username (without @), `null` if private
- `title`: Human-readable channel name
- `participants_count`: Number of members/subscribers, `null` if unavailable
- `is_broadcast`: `true` for channels, `false` for groups
- `is_megagroup`: `true` for supergroups
- `is_private`: `true` if private (requires invite/membership)
- `access_hash`: Telegram's access hash for the channel
- `description`: Channel description/bio, `null` if not available

**Frontend Actions**:
- Display channels in a browsable list
- Show channel type badges (Channel/Group, Public/Private)
- Allow user to select a channel to create a source
- Pre-fill source form with:
  - `identifier`: Use `@{username}` for public or `{id}` for private
  - `channel_title`: Use `title`
  - `access_level`: "public" if `is_private: false`, "private" if `is_private: true`
- Show participant count for context

**Use Case**: 
This endpoint is called after a session is created to help users discover which channels they can scrape. It's especially useful for private channels where users need to already be members.

**Example Flow**:
1. User creates/selects a session
2. Frontend calls `GET /sessions/{session_id}/channels`
3. Display channels in a list/grid
4. User clicks "Add to Sources" on a channel
5. Pre-populate the "Create Source" form with channel details
6. User confirms and creates the source

---

### 7. Delete Session

**Endpoint**: `DELETE /sessions/{session_id}`

**Description**: Delete a session by ID.

**Path Parameters**:
- `session_id`: integer (e.g., 1)

**Response** (200 OK):
```json
{
  "message": "Session deleted successfully"
}
```

**Frontend Actions**:
- Show confirmation dialog before deletion
- Remove session from UI after successful deletion
- **Warning**: Check if any sources are using this session before deleting

---

## 📡 Sources Management Endpoints

### 1. Create Source

**Endpoint**: `POST /sources/`

**Description**: Create a new scraping source (Telegram channel configuration).

**Request Body**:
```json
{
  "name": "Euronews English",
  "identifier": "@euronews_eng",
  "channel_title": "Euronews",
  "access_level": "public",
  "target": "LOCAL",
  "session_ref": null
}
```

**For Private Channels** (requires session):
```json
{
  "name": "Private Channel",
  "identifier": "@private_channel",
  "channel_title": "My Private Channel",
  "access_level": "private",
  "target": "NAS",
  "session_ref": 1
}
```

**Field Descriptions**:
- `name`: Friendly name for the source
- `identifier`: Telegram channel username (e.g., `@channel_name`) or ID
- `channel_title`: Human-readable channel title
- `access_level`: Either `"public"` or `"private"`
- `target`: Storage destination - `"LOCAL"`, `"NAS"`, or `"S3"`
- `session_ref`: Session ID (integer) - **Required for private channels**, `null` for public

**Response** (200 OK):
```json
{
  "id": 1,
  "name": "Euronews English",
  "identifier": "@euronews_eng",
  "channel_title": "Euronews",
  "access_level": "public",
  "target": "LOCAL",
  "session_ref": null,
  "created_at": "2025-10-30T10:10:00Z"
}
```

**Frontend Actions**:
- Show form with all fields
- For `access_level`:
  - If "public": Hide session selector, set `session_ref` to `null`
  - If "private": Show session dropdown (populated from `GET /sessions/`)
- Show success message after creation
- **Note**: Backend automatically creates a Prefect deployment for this source

---

### 2. List All Sources

**Endpoint**: `GET /sources/`

**Description**: Retrieve all configured scraping sources.

**Response** (200 OK):
```json
[
  {
    "id": 1,
    "name": "Euronews English",
    "identifier": "@euronews_eng",
    "channel_title": "Euronews",
    "access_level": "public",
    "target": "LOCAL",
    "session_ref": null,
    "created_at": "2025-10-30T10:10:00Z"
  },
  {
    "id": 2,
    "name": "Private Channel",
    "identifier": "@private_channel",
    "channel_title": "My Private Channel",
    "access_level": "private",
    "target": "NAS",
    "session_ref": 1,
    "created_at": "2025-10-30T10:15:00Z"
  }
]
```

**Frontend Actions**:
- Display sources in a table with columns:
  - Name
  - Channel Title
  - Access Level (badge: green for public, yellow for private)
  - Target Storage
  - Session (show session name if `session_ref` exists)
  - Actions (delete button)

---

### 3. Get Source by ID

**Endpoint**: `GET /sources/{source_id}`

**Description**: Retrieve a specific source by ID.

**Path Parameters**:
- `source_id`: integer (e.g., 1)

**Response** (200 OK):
```json
{
  "id": 1,
  "name": "Euronews English",
  "identifier": "@euronews_eng",
  "channel_title": "Euronews",
  "access_level": "public",
  "target": "LOCAL",
  "session_ref": null,
  "created_at": "2025-10-30T10:10:00Z"
}
```

**Frontend Actions**:
- Use for edit functionality
- Populate form with existing values

---

### 4. Delete Source

**Endpoint**: `DELETE /sources/{source_id}`

**Description**: Delete a source by ID.

**Path Parameters**:
- `source_id`: integer (e.g., 1)

**Response** (200 OK):
```json
{
  "message": "Source deleted successfully"
}
```

**Frontend Actions**:
- Show confirmation dialog
- Remove source from UI after deletion

---

## 🔗 Relationships & Data Flow

### Session → Source Relationship

```
┌─────────────────┐
│  Telegram       │
│  Session        │  (1 session)
│  (id: 1)        │
└────────┬────────┘
         │
         │ Can be used by
         │ multiple sources
         │
         ├────────────────┬────────────────┐
         │                │                │
         ▼                ▼                ▼
    ┌────────┐      ┌────────┐      ┌────────┐
    │Source 1│      │Source 2│      │Source 3│
    │Private │      │Private │      │Private │
    └────────┘      └────────┘      └────────┘
```

**Key Points**:
- One session can be referenced by **multiple sources**
- Private sources **must** have a `session_ref`
- Public sources have `session_ref: null`
- Deleting a session will fail if sources are still using it (add this check in frontend)

---

## 🎯 Frontend Implementation Guide

### Session Management Page Structure

```
┌─────────────────────────────────────────┐
│  Session Management                     │
├─────────────────────────────────────────┤
│                                         │
│  [Tab: OTP Login] [Tab: Upload File]   │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ OTP Login Flow                    │ │
│  │                                   │ │
│  │ Step 1: Phone Number              │ │
│  │ [+1234567890] [Send OTP]          │ │
│  │                                   │ │
│  │ Step 2: Verification              │ │
│  │ [OTP Code]                        │ │
│  │ [Password] (if 2FA)               │ │
│  │ [Verify]                          │ │
│  │                                   │ │
│  │ Step 3: Save                      │ │
│  │ [Finalize Session]                │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Existing Sessions                 │ │
│  │                                   │ │
│  │ • my_telegram_session             │ │
│  │   +1234567890 [Delete]            │ │
│  │                                   │ │
│  │ • another_session                 │ │
│  │   +9876543210 [Delete]            │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### Sources Management Page Structure

```
┌─────────────────────────────────────────┐
│  Sources Management                     │
├─────────────────────────────────────────┤
│                                         │
│  [+ Add New Source]                     │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Add Source Form                   │ │
│  │                                   │ │
│  │ Name: [________]                  │ │
│  │ Identifier: [@channel]            │ │
│  │ Channel Title: [________]         │ │
│  │ Access Level: (o) Public          │ │
│  │               ( ) Private         │ │
│  │ Target: [LOCAL ▼]                 │ │
│  │ Session: [Select... ▼] (if private│ │
│  │ [Create Source]                   │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │ Configured Sources                │ │
│  │                                   │ │
│  │ ┌─────────────────────────────┐   │ │
│  │ │ Euronews English            │   │ │
│  │ │ @euronews_eng | PUBLIC      │   │ │
│  │ │ Target: LOCAL               │   │ │
│  │ │              [Delete]       │   │ │
│  │ └─────────────────────────────┘   │ │
│  │                                   │ │
│  │ ┌─────────────────────────────┐   │ │
│  │ │ Private Channel             │   │ │
│  │ │ @private | PRIVATE          │   │ │
│  │ │ Session: my_telegram_session│   │ │
│  │ │ Target: NAS                 │   │ │
│  │ │              [Delete]       │   │ │
│  │ └─────────────────────────────┘   │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

---

## 🔄 Complete User Journey Examples

### Journey 1: Setting Up Public Channel Scraping

1. **No session needed** - Skip to sources page
2. Navigate to **Sources Page**
3. Click "Add New Source"
4. Fill form:
   - Name: "BBC News"
   - Identifier: "@bbcnews"
   - Channel Title: "BBC News"
   - Access Level: "Public"
   - Target: "LOCAL"
   - Session: (disabled)
5. Click "Create Source"
6. Backend creates Prefect deployment
7. Scraping starts automatically

### Journey 2: Setting Up Private Channel Scraping (OTP Flow)

1. Navigate to **Session Management Page**
2. Choose "OTP Login" tab
3. **Step 1**: Enter phone: "+1234567890", session name: "my_session"
4. Click "Send OTP"
5. Check Telegram app for code
6. **Step 2**: Enter OTP code: "12345"
7. If 2FA: Enter password
8. Click "Verify"
9. **Step 3**: Click "Finalize Session"
10. Session saved! Navigate to **Sources Page**
11. Click "Add New Source"
12. Fill form:
    - Name: "Private VIP Channel"
    - Identifier: "@vip_channel"
    - Channel Title: "VIP Channel"
    - Access Level: "Private"
    - Target: "NAS"
    - Session: Select "my_session" from dropdown
13. Click "Create Source"
14. Backend creates Prefect deployment with session
15. Scraping starts automatically

### Journey 3: Upload Existing Session File

1. Navigate to **Session Management Page**
2. Choose "Upload File" tab
3. Enter session name: "imported_session"
4. Enter phone: "+1234567890"
5. Click "Choose File" and select `.session` file
6. Click "Upload"
7. Session available immediately
8. Navigate to **Sources Page** to create sources using this session

---

## ⚠️ Error Handling

### Common Errors

| HTTP Code | Error | Cause | Frontend Action |
|-----------|-------|-------|-----------------|
| 400 | Invalid phone number | Phone format incorrect | Show validation error |
| 400 | Invalid OTP code | Wrong OTP entered | Allow retry |
| 404 | Temp session not found | Expired (5 min limit) | Restart OTP flow |
| 404 | Session not found | Session doesn't exist | Refresh session list |
| 400 | Session required for private | Missing session_ref | Show error message |
| 500 | Internal server error | Backend issue | Show generic error |

### Example Error Response

```json
{
  "detail": "Invalid OTP code"
}
```

**Frontend Actions**:
- Parse `detail` field
- Show user-friendly error message
- Provide retry mechanism

---

## 🔐 Security Notes

1. **Sessions are encrypted** in the database using Fernet encryption
2. **Temporary sessions expire** after 5 minutes
3. **No API authentication** is implemented yet (add JWT/OAuth in production)
4. **CORS is enabled** for development (configure properly for production)

---

## 📊 Data Models Summary

### TelegramSession
```typescript
{
  id: number;
  session_name: string;
  phone_number: string;
  created_at: string; // ISO 8601 datetime
}
```

### Source
```typescript
{
  id: number;
  name: string;
  identifier: string; // e.g., "@channel_name"
  channel_title: string;
  access_level: "public" | "private";
  target: "LOCAL" | "NAS" | "S3";
  session_ref: number | null; // Session ID for private channels
  created_at: string; // ISO 8601 datetime
}
```

### TempSession (Internal - Not exposed to frontend)
```typescript
{
  id: string; // UUID
  phone_number: string;
  session_name: string;
  phone_code_hash: string;
  created_at: string;
  expires_at: string;
}
```

---

## 🚀 Getting Started

### Prerequisites
- Backend running on `http://localhost:8000`
- PostgreSQL database configured
- Prefect server running

### Testing Endpoints

Use this Postman/Thunder Client collection to test:

**1. Test OTP Flow**
```bash
# Step 1
POST http://localhost:8000/sessions/send-otp
Content-Type: application/json

{
  "phone_number": "+1234567890",
  "session_name": "test_session"
}

# Step 2
POST http://localhost:8000/sessions/verify-otp
Content-Type: application/json

{
  "temp_session_id": "uuid-from-step-1",
  "code": "12345"
}

# Step 3
POST http://localhost:8000/sessions/finalize
Content-Type: application/json

{
  "temp_session_id": "uuid-from-step-1"
}
```

**2. Test Source Creation**
```bash
POST http://localhost:8000/sources/
Content-Type: application/json

{
  "name": "Test Channel",
  "identifier": "@test_channel",
  "channel_title": "Test",
  "access_level": "public",
  "target": "LOCAL",
  "session_ref": null
}
```

---

## 📞 Support

For questions or issues:
- Check Prefect UI: `http://localhost:4200`
- Check backend logs: `docker-compose logs backend`
- Verify database: `docker-compose exec postgres psql -U prefect -d prefectdb`

---

## 🎉 Summary

This API provides a complete solution for:
1. ✅ Authenticating with Telegram (OTP or file upload)
2. ✅ Managing persistent sessions
3. ✅ Configuring scraping sources
4. ✅ Automatic Prefect workflow deployment
5. ✅ Support for both public and private channels

The two-page frontend structure separates concerns:
- **Sessions Page**: Authentication and credential management
- **Sources Page**: Scraping configuration and management
