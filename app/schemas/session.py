"""
Pydantic schemas for Session management
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SessionCreate(BaseModel):
    """Schema for creating a new session (deprecated - use OTP flow instead)"""

    name: str = Field(..., description="User-friendly name for the session")
    phone_number: str = Field(..., description="Phone number used for login")
    api_id: int = Field(..., description="Telegram API ID")
    api_hash: str = Field(..., description="Telegram API Hash")
    session_string: str = Field(..., description="Telethon StringSession data")


class OTPSendRequest(BaseModel):
    """Schema for sending OTP to phone"""

    phone_number: str = Field(
        ..., description="Phone number with country code (+1234567890)"
    )
    api_id: int = Field(..., description="Telegram API ID")
    api_hash: str = Field(..., description="Telegram API Hash")


class OTPSendResponse(BaseModel):
    """Schema for OTP send response"""

    temp_session_id: str = Field(
        ..., description="Temporary session ID for verification"
    )
    phone_number: str
    message: str = "OTP sent successfully. Check your Telegram app."
    expires_in_minutes: int = 10


class OTPVerifyRequest(BaseModel):
    """Schema for verifying OTP"""

    temp_session_id: str = Field(..., description="Temporary session ID from send_otp")
    code: str = Field(..., description="OTP code from Telegram")
    password: Optional[str] = Field(None, description="2FA password if enabled")
    session_name: Optional[str] = Field(
        None, description="Optional name for the session"
    )


class SessionFileUploadResponse(BaseModel):
    """Schema for session file upload response"""

    temp_session_id: str
    phone_number: str
    message: str = "Session file uploaded. Provide a name to save."


class SessionFinalizeRequest(BaseModel):
    """Schema for finalizing session creation"""

    temp_session_id: str = Field(..., description="Temporary session ID")
    name: str = Field(..., description="User-friendly name for the session")


class SessionResponse(BaseModel):
    """Schema for session response"""

    id: str
    name: str
    phone_number: str
    api_id: int
    is_active: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChannelInfo(BaseModel):
    """Schema for channel information"""

    id: int
    username: Optional[str] = None
    title: str
    participants_count: Optional[int] = None
    is_broadcast: bool = False
    is_megagroup: bool = False
    is_private: bool
    access_hash: Optional[int] = None
    description: Optional[str] = None


class SessionUpdate(BaseModel):
    """Schema for updating session"""

    name: Optional[str] = None
    is_active: Optional[str] = None
