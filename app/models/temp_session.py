"""
Temporary session model for storing pending OTP verifications
"""

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.sql import func
from app.core.database import Base
import uuid
from datetime import datetime, timedelta, timezone


class TempSession(Base):
    """Temporary storage for sessions pending OTP verification"""

    __tablename__ = "temp_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String, nullable=False)
    api_id = Column(Integer, nullable=False)
    api_hash = Column(String, nullable=False)  # Encrypted
    session_string = Column(String, nullable=False)  # Encrypted temporary session
    phone_code_hash = Column(String, nullable=False)  # For OTP verification
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<TempSession {self.phone_number}>"

    @property
    def is_expired(self):
        """Check if temporary session has expired"""
        return datetime.now(timezone.utc) > self.expires_at
