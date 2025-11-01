from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.scrape import ScrapeStatus, LogLevel


class ScrapeLogEntry(BaseModel):
    id: UUID
    run_id: UUID
    timestamp: datetime
    level: LogLevel
    message: str
    details: Optional[dict] = None

    class Config:
        from_attributes = True


class ScrapedFileResponse(BaseModel):
    id: UUID
    run_id: UUID
    source_id: UUID
    message_id: int
    file_id: str
    file_name: str
    file_extension: Optional[str] = None
    storage_path: str
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    extracted_from: Optional[str] = None
    extra_metadata: dict = Field(default_factory=dict)
    processed_at: datetime

    class Config:
        from_attributes = True


class ScrapeRunSummary(BaseModel):
    id: UUID
    source_id: UUID
    flow_run_id: Optional[str]
    status: ScrapeStatus
    started_at: datetime
    finished_at: Optional[datetime]
    total_files_found: int
    total_files_processed: int

    class Config:
        from_attributes = True


class ScrapeRunDetail(ScrapeRunSummary):
    notes: Optional[str] = None
    logs: List[ScrapeLogEntry] = Field(default_factory=list)
    files: List[ScrapedFileResponse] = Field(default_factory=list)
