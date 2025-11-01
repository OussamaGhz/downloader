from prefect import flow, task
from app.core.database import SessionLocal
from app.models.source import Source
from app.models.session import (
    TelegramSession,
)  # Import to resolve SQLAlchemy relationship
from app.services.scraper_manager import ScraperManager
from app.services.encryption import decrypt_data


@task
def load_source_from_db(source_id: str):
    db = SessionLocal()
    source = db.query(Source).filter(Source.id == source_id).first()
    db.close()
    return source


@task
def fetch_messages(config: Source):
    # Placeholder for fetching messages
    print(f"Fetching messages for {config.name}")
    return []


@task
def download_files(messages: list, config: Source):
    # Placeholder for downloading files
    print(f"Downloading files for {config.name}")
    return []


@task
def upload_files(files: list, config: Source):
    # Placeholder for uploading files
    print(f"Uploading files for {config.name}")


@flow
def telegram_scraper_flow(source_id: str):
    """
    - Fetches source configuration from the database.
    - Initializes the appropriate scraper based on the source configuration.
    - Fetches messages, downloads files, and uploads them to the target storage.
    """
    config = load_source_from_db(source_id)

    # Decrypt sensitive data if necessary
    if config.api_hash:
        config.api_hash = decrypt_data(config.api_hash)
    if config.bot_token:
        config.bot_token = decrypt_data(config.bot_token)

    scraper = ScraperManager.get_scraper(config)

    messages = scraper.fetch_messages()
    files = scraper.download_files(messages)
    scraper.upload_files(files)
