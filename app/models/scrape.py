import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Integer,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base
import enum


class ScrapeStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    flow_run_id = Column(String, nullable=True, index=True)
    status = Column(SQLAlchemyEnum(ScrapeStatus), default=ScrapeStatus.PENDING)
    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)
    total_files_found = Column(Integer, default=0)
    total_files_processed = Column(Integer, default=0)
    notes = Column(String, nullable=True)

    source = relationship("Source", back_populates="runs")
    logs = relationship("ScrapeLog", back_populates="run", cascade="all, delete-orphan")
    files = relationship(
        "ScrapedFile", back_populates="run", cascade="all, delete-orphan"
    )


class ScrapedFile(Base):
    __tablename__ = "scraped_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("scrape_runs.id"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    message_id = Column(Integer, nullable=False)
    file_id = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_extension = Column(String, nullable=True)
    storage_path = Column(String, nullable=False)
    checksum = Column(String, nullable=True)
    archive_checksum = Column(
        String(64), nullable=True, index=True
    )  # SHA256 of archive file
    size_bytes = Column(Integer, nullable=True)
    extracted_from = Column(String, nullable=True)
    extra_metadata = Column(JSON, default=dict)
    processed_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    run = relationship("ScrapeRun", back_populates="files")
    source = relationship("Source", back_populates="files")

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "message_id",
            "file_id",
            "extracted_from",
            name="uix_source_message_file",
        ),
    )


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("scrape_runs.id"), nullable=False)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    level = Column(SQLAlchemyEnum(LogLevel), default=LogLevel.INFO)
    message = Column(String, nullable=False)
    details = Column(JSON, nullable=True)

    run = relationship("ScrapeRun", back_populates="logs")
