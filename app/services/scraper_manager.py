from app.models.source import Source, AccessLevelEnum
from typing import List


class ScraperManager:
    """
    Manages different types of scrapers based on source configuration.
    Handles public channels and private channels (with or without session).
    """

    @staticmethod
    def get_scraper(config: Source):
        """
        Returns the appropriate scraper based on the source's access level.

        - Public: Uses bot token for public channel access
        - Private: Uses user session to access private channel
        """
        if config.access_level == AccessLevelEnum.PUBLIC:
            return PublicChannelScraper(config)
        elif config.access_level == AccessLevelEnum.PRIVATE:
            return PrivateChannelScraper(config)
        else:
            raise ValueError(f"Unknown access level: {config.access_level}")


class PublicChannelScraper:
    """Scraper for public Telegram channels using bot token."""

    def __init__(self, config: Source):
        self.config = config

    def fetch_messages(self) -> List[dict]:
        """Fetch messages from public channel using bot token."""
        # TODO: Implement using Telethon or Pyrogram with bot_token
        print(f"Fetching messages from public channel: {self.config.identifier}")
        return []

    def download_files(self, messages: List[dict]) -> List[str]:
        """Download files from messages."""
        # TODO: Implement file download logic
        print(f"Downloading files for: {self.config.name}")
        return []

    def upload_files(self, files: List[str]):
        """Upload files to target storage (NAS/S3/LOCAL)."""
        # TODO: Implement upload logic based on self.config.target
        print(f"Uploading files to {self.config.target}")


class PrivateChannelScraper:
    """
    Scraper for private Telegram channels using user session.
    Handles both joinable channels (with invite link) and restricted channels (existing session).
    """

    def __init__(self, config: Source):
        self.config = config

    def fetch_messages(self) -> List[dict]:
        """
        Fetch messages from private channel using user session.

        - If session_ref exists: Use stored session file from authorized member
        - If no session_ref: Attempt to join using invite link (if available)
        """
        if self.config.session_ref:
            print(f"Fetching messages from private channel: {self.config.identifier}")
            print(f"Using session: {self.config.session_ref}")
        else:
            print(f"Fetching messages from private channel: {self.config.identifier}")
            print("No session file provided - attempting to join with invite link")

        # TODO: Load session file from self.config.session_ref if available
        # TODO: Use Telethon/Pyrogram with the existing session or join with invite
        return []

    def download_files(self, messages: List[dict]) -> List[str]:
        """Download files from messages."""
        print(f"Downloading files for: {self.config.name}")
        return []

    def upload_files(self, files: List[str]):
        """Upload files to target storage."""
        print(f"Uploading files to {self.config.target}")
