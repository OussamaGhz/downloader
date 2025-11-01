# Telegram Scraper Backend

A FastAPI-based backend for scraping Telegram channels with Prefect orchestration.

## 📚 Documentation

- **[Quick Start Guide](./QUICK_START.md)** - Start here! Fast introduction for frontend developers
- **[API Documentation](./API_DOCUMENTATION.md)** - Complete API reference with all endpoints
- **[Architecture Diagrams](./ARCHITECTURE.md)** - Visual system architecture and data flows

## 🎯 Features

- ✅ **Session Management**: Authenticate with Telegram using OTP or session file upload
- ✅ **Source Configuration**: Set up scraping for public and private Telegram channels
- ✅ **Prefect Integration**: Automatic workflow deployment and orchestration
- ✅ **Flexible Storage**: Support for LOCAL, NAS, and S3 storage targets
- ✅ **Encrypted Sessions**: Fernet encryption for stored credentials
- ✅ **Background Tasks**: Automatic cleanup of expired temporary sessions

## 🏗️ System Architecture

### Two-Page Frontend Structure

Your frontend needs **TWO separate pages**:

1. **Session Management Page** (`/sessions`)
   - Authenticate with Telegram (OTP or file upload)
   - Manage persistent sessions
   - View and delete sessions

2. **Sources Management Page** (`/sources`)
   - Configure scraping sources
   - Link private channels to sessions
   - Choose storage targets
   - View and delete sources

### Tech Stack

- **FastAPI**: REST API framework
- **PostgreSQL**: Database for sessions and sources
- **Prefect 2.x**: Workflow orchestration
- **Telethon**: Telegram client library
- **Docker**: Containerization
- **Cryptography**: Fernet encryption for sessions

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Telegram API credentials (api_id, api_hash, bot_token)

### Setup

1. **Clone and navigate to the project**:
   ```bash
   cd /path/to/backend
   ```

2. **Configure environment variables**:
   ```bash
   # Copy example env file
   cp .env.example .env
   
   # Edit .env with your credentials
   nano .env
   ```

   Required variables:
   ```env
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   BOT_TOKEN=your_bot_token
   ENCRYPTION_KEY=your_fernet_key  # Generate with generate_key.py
   ```

3. **Generate encryption key** (if needed):
   ```bash
   python generate_key.py
   ```

4. **Start services**:
   ```bash
   docker-compose up -d
   ```

5. **Verify services**:
   - Backend API: http://localhost:8000
   - Prefect UI: http://localhost:4200
   - API Docs: http://localhost:8000/docs

### Testing the API

Use the [Quick Start Guide](./QUICK_START.md) for testing examples.

## 📖 API Overview

### Session Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sessions/send-otp` | Send OTP to phone (Step 1) |
| POST | `/sessions/verify-otp` | Verify OTP/password (Step 2) |
| POST | `/sessions/finalize` | Save session (Step 3) |
| POST | `/sessions/upload-file` | Upload .session file |
| GET | `/sessions/` | List all sessions |
| GET | `/sessions/{id}/channels` | Get channels accessible by session |
| DELETE | `/sessions/{id}` | Delete a session |

### Source Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sources/` | Create a source |
| GET | `/sources/` | List all sources |
| GET | `/sources/{id}` | Get one source |
| DELETE | `/sources/{id}` | Delete a source |

For complete details, see [API_DOCUMENTATION.md](./API_DOCUMENTATION.md)

## 🔄 Workflow

### 1. Authenticate with Telegram

**Option A: OTP Flow**
```
Phone Number → OTP → Password (if 2FA) → Finalize
```

**Option B: Upload Session File**
```
Upload .session file → Done
```

### 2. Configure Scraping Source

- Create source with channel identifier
- Select access level (public/private)
- Link to session (for private channels)
- Choose storage target

### 3. Automatic Scraping

- Backend creates Prefect deployment
- Prefect agent executes scraping workflow
- Content downloaded and stored automatically

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── api/
│   │   ├── routes_sessions.py  # Session management endpoints
│   │   └── routes_sources.py   # Source management endpoints
│   ├── core/
│   │   ├── config.py          # Configuration
│   │   └── database.py        # Database connection
│   ├── models/
│   │   ├── session.py         # TelegramSession model
│   │   ├── temp_session.py    # TempSession model
│   │   └── source.py          # Source model
│   ├── schemas/
│   │   ├── session.py         # Pydantic schemas
│   │   └── source.py
│   ├── services/
│   │   ├── telegram_client.py # Telegram operations
│   │   ├── encryption.py      # Fernet encryption
│   │   ├── scraper_manager.py # Scraper factory
│   │   ├── prefect_client.py  # Prefect deployment
│   │   └── cleanup.py         # Background tasks
│   └── prefect_flows/
│       └── telegram_flow.py   # Scraping workflow
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🔐 Security

- **Encrypted Sessions**: All session data is encrypted using Fernet (symmetric encryption)
- **Environment Variables**: Sensitive credentials stored in .env file
- **Temporary Sessions**: Auto-expire after 5 minutes
- **Background Cleanup**: Regular cleanup of expired temp sessions

## 🐛 Troubleshooting

### Docker Issues

```bash
# Restart all services
docker-compose restart

# View logs
docker-compose logs backend
docker-compose logs prefect-server

# Recreate database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d
```

### Database Issues

```bash
# Access PostgreSQL
docker-compose exec postgres psql -U prefect -d prefectdb

# Check tables
\dt

# View sessions
SELECT * FROM telegram_sessions;
```

### Prefect Issues

```bash
# Check Prefect UI
# Visit http://localhost:4200

# View deployments
docker-compose exec backend prefect deployment ls

# View flow runs
docker-compose exec backend prefect flow-run ls
```

## 📊 Database Schema

### TelegramSession
- `id`: Primary key
- `session_name`: Unique session identifier
- `phone_number`: User's phone number
- `encrypted_data`: Fernet-encrypted session data
- `created_at`: Timestamp

### Source
- `id`: Primary key
- `name`: Friendly name
- `identifier`: Channel username or ID
- `channel_title`: Channel display name
- `access_level`: "public" or "private"
- `target`: "LOCAL", "NAS", or "S3"
- `session_ref`: Foreign key to TelegramSession (nullable)
- `created_at`: Timestamp

### TempSession (temporary)
- `id`: UUID
- `phone_number`: User's phone
- `session_name`: Desired session name
- `phone_code_hash`: Telegram verification hash
- `encrypted_data`: Encrypted session state
- `created_at`: Timestamp
- `expires_at`: Auto-cleanup timestamp (5 min)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📝 License

[Your License Here]

## 📞 Support

For questions or issues:
- Check the [Quick Start Guide](./QUICK_START.md)
- Review [API Documentation](./API_DOCUMENTATION.md)
- Check Prefect UI logs
- Review Docker logs

## 🎉 Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/)
- [Prefect](https://www.prefect.io/)
- [Telethon](https://docs.telethon.dev/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Cryptography](https://cryptography.io/)
