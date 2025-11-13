import os
from dotenv import load_dotenv

load_dotenv()

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# Prefect Configuration
PREFECT_API_URL = os.getenv("PREFECT_API_URL")

# NAS/SMB Storage Configuration
NAS_SERVER = os.getenv("NAS_SERVER", "10.200.0.200")
NAS_SHARE = os.getenv("NAS_SHARE", "LEAKSPARK")
NAS_USERNAME = os.getenv("NAS_USERNAME", "admin")
NAS_PASSWORD = os.getenv("NAS_PASSWORD", "")
NAS_PORT = int(os.getenv("NAS_PORT", "445"))

# Telegram Scraper - Batch and Concurrency Settings
MAX_FILES_PER_RUN = int(os.getenv("MAX_FILES_PER_RUN", "10"))
DOWNLOAD_CONCURRENCY = int(os.getenv("DOWNLOAD_CONCURRENCY", "3"))

# Telegram Scraper - Retry Settings
DOWNLOAD_RETRY_ATTEMPTS = int(os.getenv("DOWNLOAD_RETRY_ATTEMPTS", "3"))
DOWNLOAD_RETRY_BASE_DELAY = int(os.getenv("DOWNLOAD_RETRY_BASE_DELAY", "2"))

# Telegram Scraper - Timeout Configurations (in seconds)
DOWNLOAD_TIMEOUT_PER_FILE = int(
    os.getenv("DOWNLOAD_TIMEOUT_PER_FILE", "1800")
)  # 30 min
DOWNLOAD_TASK_BASE_TIMEOUT = int(
    os.getenv("DOWNLOAD_TASK_BASE_TIMEOUT", "14400")
)  # 4 hours
PROCESS_FILE_TIMEOUT = int(os.getenv("PROCESS_FILE_TIMEOUT", "3600"))  # 1 hour
