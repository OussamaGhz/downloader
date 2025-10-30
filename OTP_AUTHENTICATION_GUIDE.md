# Interactive OTP Authentication Flow

This document describes the two methods for authenticating Telegram sessions in the API.

## Overview

The API supports two authentication methods:
1. **Interactive OTP Flow**: Users provide phone number and API credentials, receive OTP, and verify it
2. **Session File Upload**: Users upload an existing `.session` file

Both methods result in a permanent `TelegramSession` stored in the database.

---

## Method 1: Interactive OTP Flow

### Step 1: Send OTP

**Endpoint**: `POST /sessions/send-otp`

**Request Body**:
```json
{
  "phone_number": "+1234567890",
  "api_id": 12345678,
  "api_hash": "your_api_hash_here"
}
```

**Response** (200 OK):
```json
{
  "temp_session_id": "uuid-string",
  "phone_number": "+1234567890",
  "message": "OTP sent to your Telegram app. Enter the code to continue.",
  "expires_in_minutes": 10
}
```

**What happens**:
- Backend sends OTP to the phone number via Telegram
- Creates a temporary session (expires in 10 minutes)
- Returns `temp_session_id` for next step

**Frontend Action**: 
- Display input field for OTP code
- If 2FA enabled, also show password input
- Store `temp_session_id`

---

### Step 2: Verify OTP

**Endpoint**: `POST /sessions/verify-otp`

**Request Body**:
```json
{
  "temp_session_id": "uuid-from-step-1",
  "code": "12345",
  "session_name": "My Telegram Account",
  "password": "optional_2fa_password"
}
```

**Response** (200 OK):
```json
{
  "id": "session-uuid",
  "name": "My Telegram Account",
  "phone_number": "+1234567890",
  "api_id": 12345678,
  "is_active": "active",
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

**What happens**:
- Backend verifies OTP code with Telegram
- If 2FA enabled, verifies password
- Creates permanent session with encrypted credentials
- Deletes temporary session
- Session is now ready to use

**Errors**:
- `404`: Temporary session not found or expired
- `400`: Invalid OTP code or password
- `400`: Phone number already has a session

---

## Method 2: Session File Upload

### Step 1: Upload Session File

**Endpoint**: `POST /sessions/upload-file`

**Request** (multipart/form-data):
```
api_id: 12345678
api_hash: your_api_hash_here
session_file: [file upload: mysession.session]
```

**Response** (200 OK):
```json
{
  "temp_session_id": "uuid-string",
  "phone_number": "+1234567890",
  "message": "Session file uploaded for +1234567890. Provide a name to save."
}
```

**What happens**:
- Backend reads `.session` file
- Converts to StringSession format
- Extracts phone number from session
- Creates temporary session (expires in 1 hour)

---

### Step 2: Finalize Session

**Endpoint**: `POST /sessions/finalize`

**Request Body**:
```json
{
  "temp_session_id": "uuid-from-upload",
  "name": "Production Account"
}
```

**Response** (200 OK):
```json
{
  "id": "session-uuid",
  "name": "Production Account",
  "phone_number": "+1234567890",
  "api_id": 12345678,
  "is_active": "active",
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

**What happens**:
- Backend creates permanent session
- Deletes temporary session
- Session is now ready to use

---

## Session Management

### Get All Sessions

**Endpoint**: `GET /sessions/`

**Query Parameters**:
- `skip`: Pagination offset (default: 0)
- `limit`: Max results (default: 100)

**Response**:
```json
[
  {
    "id": "uuid",
    "name": "Session 1",
    "phone_number": "+1234567890",
    "api_id": 12345678,
    "is_active": "active",
    "created_at": "2024-01-01T12:00:00",
    "updated_at": "2024-01-01T12:00:00"
  }
]
```

---

### Get Session Details

**Endpoint**: `GET /sessions/{session_id}`

**Response**: Single session object (same as above)

---

### Get Accessible Channels

**Endpoint**: `GET /sessions/{session_id}/channels`

**Response**:
```json
[
  {
    "id": 1234567890,
    "title": "My Channel",
    "username": "mychannel",
    "is_channel": true,
    "is_group": false,
    "is_private": false,
    "participants_count": 1000
  }
]
```

**What happens**:
- Uses session to fetch all channels/groups accessible to user
- Returns list with metadata

---

### Test Session Validity

**Endpoint**: `POST /sessions/{session_id}/test`

**Response**:
```json
{
  "session_id": "uuid",
  "is_valid": true,
  "status": "active"
}
```

**What happens**:
- Tests if session is still authorized with Telegram
- Updates `is_active` status if expired

---

### Update Session

**Endpoint**: `PUT /sessions/{session_id}`

**Request Body**:
```json
{
  "name": "New Name",
  "is_active": "inactive"
}
```

**Response**: Updated session object

---

### Delete Session

**Endpoint**: `DELETE /sessions/{session_id}`

**Response**:
```json
{
  "message": "Session deleted successfully",
  "id": "uuid"
}
```

**Errors**:
- `400`: Cannot delete if sources are using this session

---

### Cancel Temporary Session

**Endpoint**: `DELETE /sessions/temp/{temp_session_id}`

**Response**:
```json
{
  "message": "Temporary session cancelled",
  "id": "uuid"
}
```

**Use case**: User abandons OTP flow and wants to start over

---

## Security Features

### Encryption
- All sensitive data encrypted at rest:
  - `api_hash`: Encrypted with Fernet symmetric encryption
  - `session_string`: Encrypted with Fernet
  - `phone_code_hash`: Encrypted during OTP flow

### Temporary Sessions
- Expire after 10 minutes (OTP flow) or 1 hour (file upload)
- Automatically cleaned up by background task every 5 minutes
- Cannot be reused after verification

### No Logging
- OTP codes never logged
- API credentials never logged
- Session strings never logged

### Session Validation
- Phone numbers are unique (one session per phone)
- Sessions tested before use in scraping flows
- Invalid sessions marked as "expired"

---

## Frontend Integration Examples

### React Example (OTP Flow)

```javascript
// Step 1: Send OTP
const sendOTP = async (phoneNumber, apiId, apiHash) => {
  const response = await fetch('/sessions/send-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      phone_number: phoneNumber,
      api_id: apiId,
      api_hash: apiHash
    })
  });
  
  const data = await response.json();
  return data.temp_session_id; // Save this for step 2
};

// Step 2: Verify OTP
const verifyOTP = async (tempSessionId, code, sessionName, password = null) => {
  const response = await fetch('/sessions/verify-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      temp_session_id: tempSessionId,
      code: code,
      session_name: sessionName,
      password: password
    })
  });
  
  const session = await response.json();
  return session; // Permanent session created!
};
```

### React Example (File Upload)

```javascript
// Step 1: Upload file
const uploadSessionFile = async (file, apiId, apiHash) => {
  const formData = new FormData();
  formData.append('session_file', file);
  formData.append('api_id', apiId);
  formData.append('api_hash', apiHash);
  
  const response = await fetch('/sessions/upload-file', {
    method: 'POST',
    body: formData
  });
  
  const data = await response.json();
  return data.temp_session_id;
};

// Step 2: Finalize
const finalizeSession = async (tempSessionId, name) => {
  const response = await fetch('/sessions/finalize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      temp_session_id: tempSessionId,
      name: name
    })
  });
  
  const session = await response.json();
  return session;
};
```

---

## Error Handling

### Common Errors

| Status Code | Error | Cause | Solution |
|-------------|-------|-------|----------|
| 400 | Invalid phone number | Phone format incorrect | Use international format: +1234567890 |
| 400 | Session already exists | Phone already registered | Delete existing session first |
| 400 | Temporary session expired | > 10 min since OTP sent | Request new OTP |
| 400 | Invalid OTP code | Wrong code entered | Check Telegram app and retry |
| 400 | Invalid password | 2FA password incorrect | Verify 2FA password |
| 404 | Temporary session not found | Invalid temp_session_id | Start flow again |
| 500 | Failed to send OTP | API credentials invalid | Verify api_id and api_hash |

---

## Database Schema

### `telegram_sessions` (Permanent)
```sql
CREATE TABLE telegram_sessions (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    phone_number VARCHAR UNIQUE NOT NULL,
    api_id INTEGER NOT NULL,
    api_hash VARCHAR NOT NULL,  -- Encrypted
    session_string TEXT NOT NULL,  -- Encrypted
    is_active VARCHAR DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### `temp_sessions` (Temporary)
```sql
CREATE TABLE temp_sessions (
    id VARCHAR PRIMARY KEY,
    phone_number VARCHAR NOT NULL,
    api_id INTEGER NOT NULL,
    api_hash VARCHAR NOT NULL,  -- Encrypted
    session_string TEXT NOT NULL,  -- Encrypted
    phone_code_hash VARCHAR NOT NULL,  -- Encrypted
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);
```

---

## Background Tasks

### Cleanup Service
- **Task**: Delete expired temporary sessions
- **Schedule**: Every 5 minutes
- **Location**: `app/services/cleanup.py`
- **Auto-start**: Yes (via FastAPI lifespan)

---

## Testing

### Manual Testing with cURL

```bash
# Step 1: Send OTP
curl -X POST http://localhost:8000/sessions/send-otp \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "api_id": 12345678,
    "api_hash": "your_api_hash"
  }'

# Step 2: Verify OTP
curl -X POST http://localhost:8000/sessions/verify-otp \
  -H "Content-Type: application/json" \
  -d '{
    "temp_session_id": "uuid-from-step-1",
    "code": "12345",
    "session_name": "Test Session"
  }'

# Get all sessions
curl http://localhost:8000/sessions/

# Get channels
curl http://localhost:8000/sessions/{session_id}/channels
```

---

## Best Practices

1. **OTP Flow**:
   - Always show remaining time to user (10 minutes)
   - Handle 2FA password field conditionally
   - Clear sensitive form fields after submission

2. **File Upload**:
   - Validate file extension (.session) on frontend
   - Show preview of phone number after upload
   - Allow user to cancel before finalizing

3. **Error Handling**:
   - Show user-friendly error messages
   - Provide "start over" button on errors
   - Log errors on backend without exposing credentials

4. **Session Management**:
   - Test sessions periodically
   - Mark inactive sessions clearly in UI
   - Warn before deleting sessions with active sources

---

## Migration from Old System

If you have existing sessions stored differently:

1. Use file upload method with existing `.session` files
2. Or re-authenticate with OTP flow
3. Old session strings can be encrypted and migrated directly to database

---

## Troubleshooting

### "Failed to send OTP"
- Verify `api_id` and `api_hash` are correct
- Ensure phone number is in international format
- Check if number is already registered on another account

### "Temporary session not found"
- Session expired (>10 min for OTP, >1 hour for file)
- Restart the flow from beginning

### "Invalid OTP code"
- Check Telegram app for correct code
- Ensure code is entered within 10 minutes
- Try resending OTP

### "Cannot delete session"
- Session is being used by active sources
- Delete or reassign sources first
- Then delete session

---

## API Version

**Current Version**: 2.0.0

**Changes from 1.0**:
- Added interactive OTP flow
- Added session file upload
- Removed direct session string upload
- Added temporary session mechanism
- Added automatic cleanup
- Enhanced security with encryption
