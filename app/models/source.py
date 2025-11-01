import uuid
from sqlalchemy import (
    Column,
    String,
    DateTime,
    JSON,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class TargetEnum(str, enum.Enum):
    NAS = "NAS"
    S3 = "S3"
    LOCAL = "LOCAL"


class AccessLevelEnum(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class Source(Base):
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)

    # Telegram API credentials (required for all sources)
    api_id = Column(String, nullable=False)  # Encrypted
    api_hash = Column(String, nullable=False)  # Encrypted

    # Channel information
    access_level = Column(SQLAlchemyEnum(AccessLevelEnum), nullable=False)
    identifier = Column(String, nullable=False)  # Channel username or ID
    channel_title = Column(String)  # Display name of the channel

    # Session reference (for private channels)
    session_ref = Column(String, ForeignKey("telegram_sessions.id"), nullable=True)
    session = relationship("TelegramSession", backref="sources")

    # Bot token (optional - for public channels)
    bot_token = Column(String, nullable=True)  # Encrypted

    # Scraping configuration
    file_types = Column(JSON, default=list)  # ['pdf', 'zip', 'jpg']
    target = Column(SQLAlchemyEnum(TargetEnum), nullable=False)
    target_path = Column(String)  # Specific path in target storage

    # Scheduling
    schedule = Column(String)  # Cron expression
    is_active = Column(String, default="active")

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_scraped_at = Column(DateTime(timezone=True))

    # Statistics
    total_messages_scraped = Column(Integer, default=0)
    total_files_downloaded = Column(Integer, default=0)
