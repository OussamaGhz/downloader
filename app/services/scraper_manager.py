from app.models.source import Source, AccessLevelEnum
from typing import List


class ScraperManager:
    """
    Manages different types of scrapers based on source configuration.
    Handles public channels, private joinable channels, and private restricted channels.
    """

    @staticmethod
    def get_scraper(config: Source):
        """
        Returns the appropriate scraper based on the source's access level.

        - Public: Uses bot token for public channel access
        - Private Joinable: Uses user session to join and scrape
        - Private Restricted: Uses existing session file from authorized member
        """
        if config.access_level == AccessLevelEnum.PUBLIC:
            return PublicChannelScraper(config)
        elif config.access_level == AccessLevelEnum.PRIVATE_JOINABLE:
            return PrivateJoinableScraper(config)
        elif config.access_level == AccessLevelEnum.PRIVATE_RESTRICTED:
            return PrivateRestrictedScraper(config)
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


class PrivateJoinableScraper:
    """Scraper for private channels that can be joined with invite link."""

    def __init__(self, config: Source):
        self.config = config

    def fetch_messages(self) -> List[dict]:
        """Fetch messages from private joinable channel using user session."""
        # TODO: Implement using Telethon/Pyrogram with api_id, api_hash
        # Join channel using invite link if not already a member
        print(
            f"Fetching messages from private joinable channel: {self.config.identifier}"
        )
        return []

    def download_files(self, messages: List[dict]) -> List[str]:
        """Download files from messages."""
        print(f"Downloading files for: {self.config.name}")
        return []

    def upload_files(self, files: List[str]):
        """Upload files to target storage."""
        print(f"Uploading files to {self.config.target}")


class PrivateRestrictedScraper:
    """Scraper for private restricted channels using existing authorized session."""

    def __init__(self, config: Source):
        self.config = config

    def fetch_messages(self) -> List[dict]:
        """Fetch messages using stored session file from authorized member."""
        # TODO: Load session file from self.config.session_ref
        # Use Telethon/Pyrogram with the existing session
        print(
            f"Fetching messages from private restricted channel: {self.config.identifier}"
        )
        print(f"Using session: {self.config.session_ref}")
        return []

    def download_files(self, messages: List[dict]) -> List[str]:
        """Download files from messages."""
        print(f"Downloading files for: {self.config.name}")
        return []

    def upload_files(self, files: List[str]):
        """Upload files to target storage."""
        print(f"Uploading files to {self.config.target}")
