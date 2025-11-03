from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, Set, Tuple
from uuid import UUID as UUIDType
import logging

# Note: avoid importing sqlalchemy.exc directly to prevent linter/import issues

from app.core.database import SessionLocal
from app.models.scrape import (
    LogLevel,
    ScrapeLog,
    ScrapeRun,
    ScrapeStatus,
    ScrapedFile,
)


@contextmanager
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _to_uuid(value: str) -> UUIDType:
    if isinstance(value, UUIDType):
        return value
    return UUIDType(str(value))


def create_scrape_run(source_id: str, flow_run_id: Optional[str] = None) -> ScrapeRun:
    with get_db_session() as db:
        run = ScrapeRun(
            source_id=_to_uuid(source_id),
            flow_run_id=flow_run_id,
            status=ScrapeStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def mark_run_complete(run_id: str, status: ScrapeStatus, notes: Optional[str] = None):
    with get_db_session() as db:
        run_uuid = _to_uuid(run_id)
        run = db.query(ScrapeRun).filter(ScrapeRun.id == run_uuid).first()
        if not run:
            return
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        if notes:
            run.notes = notes
        db.commit()


def update_run_counts(
    run_id: str,
    files_found: Optional[int] = None,
    files_processed: Optional[int] = None,
):
    with get_db_session() as db:
        run_uuid = _to_uuid(run_id)
        run = db.query(ScrapeRun).filter(ScrapeRun.id == run_uuid).first()
        if not run:
            return
        if files_found is not None:
            run.total_files_found = files_found
        if files_processed is not None:
            run.total_files_processed = files_processed
        db.commit()


def log_event(
    run_id: str,
    message: str,
    level: LogLevel = LogLevel.INFO,
    details: Optional[Dict] = None,
) -> Optional[ScrapeLog]:
    logger = logging.getLogger(__name__)
    with get_db_session() as db:
        # Ensure the referenced run exists before inserting a log entry.
        run_uuid = _to_uuid(run_id)
        run = db.query(ScrapeRun).filter(ScrapeRun.id == run_uuid).first()
        if not run:
            # Defensive behavior: do not write log entries referencing a
            # non-existent run. Log locally and return None; the caller
            # should create the run before attempting to persist logs.
            logger.warning(
                "log_event: attempt to write log for missing run %s - message=%s",
                run_id,
                message,
            )
            return None

        log_entry = ScrapeLog(
            run_id=run_uuid,
            level=level,
            message=message,
            details=details,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry


def record_scraped_file(
    run_id: str,
    source_id: str,
    message_id: int,
    file_id: str,
    file_name: str,
    storage_path: str,
    file_extension: Optional[str] = None,
    size_bytes: Optional[int] = None,
    checksum: Optional[str] = None,
    extracted_from: Optional[str] = None,
    extra_metadata: Optional[Dict] = None,
) -> Optional[ScrapedFile]:
    with get_db_session() as db:
        file_entry = ScrapedFile(
            run_id=_to_uuid(run_id),
            source_id=_to_uuid(source_id),
            message_id=message_id,
            file_id=file_id,
            file_name=file_name,
            file_extension=file_extension,
            storage_path=storage_path,
            size_bytes=size_bytes,
            checksum=checksum,
            extracted_from=extracted_from,
            extra_metadata=extra_metadata or {},
        )
        db.add(file_entry)
        try:
            db.commit()
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception(
                "record_scraped_file: failed to commit scraped file (run=%s, message=%s, file_id=%s): %s",
                run_id,
                message_id,
                file_id,
                e,
            )
            db.rollback()
            return None
        db.refresh(file_entry)
        return file_entry


def get_processed_file_keys(source_id: str) -> Set[Tuple[int, str]]:
    with get_db_session() as db:
        source_uuid = _to_uuid(source_id)
        rows = (
            db.query(ScrapedFile.message_id, ScrapedFile.file_id)
            .filter(ScrapedFile.source_id == source_uuid)
            .all()
        )
        return {(message_id, file_id) for message_id, file_id in rows}
