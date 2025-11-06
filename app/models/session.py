from sqlalchemy import Column, String, DateTime, LargeBinary, Integer, Text, Enum
from sqlalchemy.sql import func
from app.core.database import Base
import uuid


class TelegramSession(Base):
    """Model for storing Telegram session files"""

    __tablename__ = "telegram_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)  # User-friendly name for the session
    phone_number = Column(
        String, nullable=False, unique=True
    )  # Phone number used for login
    session_string = Column(
        Text, nullable=False
    )  # Encrypted Telethon StringSession data
    api_id = Column(Integer, nullable=False)  # Telegram API ID
    api_hash = Column(String, nullable=False)  # Encrypted Telegram API hash
    is_active = Column(String, default="active")  # active, expired, revoked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    privacy = Column(
        Enum("PRIVATE", "PUBLIC", name="telegram_session_privacy"),
        nullable=True,
    )

    def __repr__(self):
        return f"<TelegramSession {self.name} - {self.phone_number}>"
