from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.models.source import TargetEnum, AccessLevelEnum


class SourceCreatePrivate(BaseModel):
    """Schema for creating a private channel source"""

    name: str = Field(..., description="Source name")
    api_id: int = Field(..., description="Telegram API ID")
    api_hash: str = Field(..., description="Telegram API Hash")
    session_id: str = Field(..., description="Reference to stored session")
    channel_id: int = Field(..., description="Channel ID from Telegram")
    channel_title: str = Field(..., description="Channel display name")
    file_types: List[str] = Field(default=[], description="File types to download")
    target: TargetEnum = Field(default=TargetEnum.LOCAL, description="Storage target")
    target_path: Optional[str] = Field(
        None, description="Specific path in target storage"
    )
    schedule: Optional[str] = Field(None, description="Cron expression for scheduling")


class SourceCreatePublic(BaseModel):
    """Schema for creating a public channel source"""

    name: str = Field(..., description="Source name")
    api_id: int = Field(..., description="Telegram API ID")
    api_hash: str = Field(..., description="Telegram API Hash")
    channel_username: str = Field(..., description="Channel username or ID")
    bot_token: Optional[str] = Field(None, description="Optional bot token")
    file_types: List[str] = Field(default=[], description="File types to download")
    target: TargetEnum = Field(default=TargetEnum.LOCAL, description="Storage target")
    target_path: Optional[str] = Field(
        None, description="Specific path in target storage"
    )
    schedule: Optional[str] = Field(None, description="Cron expression for scheduling")


class SourceResponse(BaseModel):
    """Schema for source response"""

    id: UUID
    name: str
    access_level: AccessLevelEnum
    identifier: str
    channel_title: Optional[str] = None
    file_types: List[str]
    target: TargetEnum
    target_path: Optional[str] = None
    schedule: Optional[str] = None
    is_active: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_scraped_at: Optional[datetime] = None
    total_messages_scraped: int = 0
    total_files_downloaded: int = 0

    class Config:
        from_attributes = True


class SourceUpdate(BaseModel):
    """Schema for updating a source"""

    name: Optional[str] = None
    schedule: Optional[str] = None
    file_types: Optional[List[str]] = None
    target_path: Optional[str] = None
    is_active: Optional[str] = None
