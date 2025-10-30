# Telethon Session Generation Guide

## 🎯 Overview

To use private Telegram channels, you need to generate a Telethon StringSession. This guide shows you how.

---

## 📋 Prerequisites

1. Python 3.7+
2. Telegram account (phone number)
3. Telegram API credentials from https://my.telegram.org

---

## 🔧 Installation

```bash
pip install telethon
```

---

## 📱 Getting API Credentials

1. Visit https://my.telegram.org
2. Log in with your phone number
3. Go to "API development tools"
4. Create an application
5. Note down:
   - `api_id` (integer)
   - `api_hash` (string)

---

## 🔑 Generate Session String

Create a file `generate_session.py`:

```python
from telethon import TelegramClient
from telethon.sessions import StringSession

# Your API credentials from https://my.telegram.org
API_ID = 12345678  # Replace with your api_id
API_HASH = 'your_api_hash_here'  # Replace with your api_hash

async def main():
    # Create client with StringSession
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        print("Session String:")
        print(client.session.save())

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
```

---

## ▶️ Run the Script

```bash
python generate_session.py
```

**You will be prompted for:**
1. Phone number (with country code: +1234567890)
2. Verification code (sent to your Telegram app)
3. 2FA password (if enabled)

**Output:**
```
Session String:
1ApWapzMBu1Fk...very_long_string...zMBu1Fk1Ap
```

**Save this string! You'll use it in the API.**

---

## 🔒 Security Notes

- Never share your session string publicly
- Each session string gives full access to your Telegram account
- The session string is stored encrypted in the database
- You can revoke sessions from Telegram settings

---

## 📤 Upload to API

Once you have the session string:

```bash
curl -X POST http://localhost:8000/sessions/ \
  -F "name=My Personal Account" \
  -F "phone_number=+1234567890" \
  -F "api_id=12345678" \
  -F "api_hash=your_api_hash" \
  -F "session_string=1ApWapzMBu1Fk...your_session_string_here"
```

Or using Python:

```python
import requests

data = {
    "name": "My Personal Account",
    "phone_number": "+1234567890",
    "api_id": 12345678,
    "api_hash": "your_api_hash",
    "session_string": "1ApWapzMBu1Fk...your_session_string_here"
}

response = requests.post("http://localhost:8000/sessions/", data=data)
print(response.json())
```

---

## ✅ Verify Session

After uploading, test it:

```bash
# Get session ID from the create response
SESSION_ID="your-session-uuid"

# Test the session
curl -X POST http://localhost:8000/sessions/$SESSION_ID/test

# Get channels
curl http://localhost:8000/sessions/$SESSION_ID/channels
```

---

## 🔄 Using the Session

Now you can:

1. **List channels** accessible by this session
```bash
GET /sessions/{session_id}/channels
```

2. **Create sources** for private channels
```bash
POST /sources/private
{
  "session_id": "your-session-uuid",
  "channel_id": 1234567890,
  ...
}
```

---

## 🆘 Troubleshooting

### "Session is not authorized"
- Session string is invalid
- Session has expired
- Account logged out from Telegram

**Solution**: Generate a new session string

### "Phone number flood"
- Too many login attempts
- Wait 24 hours before trying again

### "API ID/Hash invalid"
- Wrong credentials
- Get new ones from https://my.telegram.org

---

## 📚 Alternative: Using Existing .session File

If you already have a `.session` file from previous Telethon use:

```python
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 12345678
API_HASH = 'your_api_hash'
SESSION_FILE = 'my_account'  # Without .session extension

async def convert_to_string():
    async with TelegramClient(SESSION_FILE, API_ID, API_HASH) as client:
        string_session = StringSession.save(client.session)
        print("String Session:")
        print(string_session)

if __name__ == '__main__':
    import asyncio
    asyncio.run(convert_to_string())
```

---

## 🎓 Best Practices

1. **One session per account**: Don't reuse session strings across multiple apps
2. **Separate accounts**: Use different Telegram accounts for scraping vs personal use
3. **Monitor sessions**: Use Telegram's "Active Sessions" to monitor logged-in devices
4. **Revoke when done**: Delete sessions from API when no longer needed
5. **2FA recommended**: Enable two-factor authentication on scraper accounts

---

## 🔐 Session Lifecycle

```
Generate Session String
  ↓
Upload to API (encrypted storage)
  ↓
Use for accessing private channels
  ↓
Monitor with /sessions/{id}/test
  ↓
Delete when done (via API)
  ↓
Optionally revoke from Telegram app
```

---

## 📝 Example Complete Flow

```python
from telethon import TelegramClient
from telethon.sessions import StringSession
import requests

API_ID = 12345678
API_HASH = 'your_api_hash'
PHONE = '+1234567890'
API_URL = 'http://localhost:8000'

async def setup_scraper():
    # Step 1: Generate session
    print("Generating session...")
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_string = client.session.save()
    
    # Step 2: Upload to API
    print("Uploading session...")
    response = requests.post(f"{API_URL}/sessions/", data={
        "name": "Scraper Account",
        "phone_number": PHONE,
        "api_id": API_ID,
        "api_hash": API_HASH,
        "session_string": session_string
    })
    session_data = response.json()
    session_id = session_data['id']
    print(f"Session created: {session_id}")
    
    # Step 3: Get channels
    print("Fetching channels...")
    channels = requests.get(f"{API_URL}/sessions/{session_id}/channels").json()
    
    for ch in channels:
        print(f"- {ch['title']} (ID: {ch['id']})")
    
    # Step 4: Create source for first channel
    if channels:
        first_channel = channels[0]
        print(f"\nCreating source for: {first_channel['title']}")
        
        source = requests.post(f"{API_URL}/sources/private", json={
            "name": f"Scraper for {first_channel['title']}",
            "api_id": API_ID,
            "api_hash": API_HASH,
            "session_id": session_id,
            "channel_id": first_channel['id'],
            "channel_title": first_channel['title'],
            "file_types": ["pdf", "zip"],
            "target": "LOCAL",
            "schedule": "0 */6 * * *"
        })
        
        print(f"Source created: {source.json()['id']}")

if __name__ == '__main__':
    import asyncio
    asyncio.run(setup_scraper())
```

---

## 🚀 Ready to Use

Your session is now ready! The scraper will:
- Automatically access private channels using this session
- Download files based on your configuration
- Run on the schedule you specified
- Keep statistics on messages and files processed

Monitor progress in Prefect UI: http://localhost:4200
