# Session Routes

All endpoints live under the `/sessions` prefix and use JSON unless noted.

## POST `/sessions/send-otp`

- **Purpose:** Start the OTP-based login flow.
- **Request body:** `OTPSendRequest`
  - `phone_number` (string, E.164)
  - `api_id` (integer)
  - `api_hash` (string)
- **Response:** `OTPSendResponse`
  - `temp_session_id` (string)
  - `phone_number` (string)
  - `message` (string)
  - `expires_in_minutes` (integer)

## POST `/sessions/verify-otp`

- **Purpose:** Verify the OTP and create a permanent session.
- **Request body:** `OTPVerifyRequest`
  - `temp_session_id` (string)
  - `code` (string)
  - `password` (string, optional 2FA)
  - `session_name` (string, optional)
- **Response:** `SessionResponse`
  - `id`, `name`, `phone_number`, `api_id`, `is_active`, `created_at`, `updated_at`

## POST `/sessions/upload-file`

- **Purpose:** Import an existing `.session` file instead of using OTP.
- **Request:** `multipart/form-data`
  - `api_id` (integer form field)
  - `api_hash` (string form field)
  - `session_file` (file field, must end with `.session`)
- **Response:** `SessionFileUploadResponse`
  - `temp_session_id`, `phone_number`, `message`

## POST `/sessions/finalize`

- **Purpose:** Promote an uploaded session file to a permanent session.
- **Request body:** `SessionFinalizeRequest`
  - `temp_session_id` (string)
  - `name` (string)
- **Response:** `SessionResponse`

## GET `/sessions/`

- **Purpose:** List stored sessions.
- **Query params:** `skip` (int, default 0), `limit` (int, default 100).
- **Response:** `List[SessionResponse]`

## GET `/sessions/{session_id}`

- **Purpose:** Retrieve a specific session.
- **Response:** `SessionResponse`

## GET `/sessions/{session_id}/channels`

- **Purpose:** Fetch channels/groups available to a session.
- **Response:** `List[ChannelInfo]`
  - Fields: `id`, `username`, `title`, `participants_count`, `is_broadcast`, `is_megagroup`, `is_private`, `access_hash`, `description`

## POST `/sessions/{session_id}/test`

- **Purpose:** Check whether the session is still valid.
- **Response:** JSON object with `session_id`, `is_valid`, `status`, and optional `error`.

## PUT `/sessions/{session_id}`

- **Purpose:** Update session metadata.
- **Request body:** `SessionUpdate`
  - `name` (string, optional)
  - `is_active` (string, optional)
- **Response:** `SessionResponse`

## DELETE `/sessions/{session_id}`

- **Purpose:** Delete a session (disallowed if it is attached to sources).
- **Response:** `{ "message": string, "id": string }`

## DELETE `/sessions/temp/{temp_session_id}`

- **Purpose:** Cancel an in-progress OTP or file-upload flow.
- **Response:** `{ "message": string, "id": string }`
