from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scrape import ScrapeLog, ScrapeRun, ScrapedFile
from app.services.prefect_client import prefect_client
from app.schemas.scrape import (
    ScrapeLogEntry,
    ScrapeRunDetail,
    ScrapeRunSummary,
    ScrapedFileResponse,
)

router = APIRouter(tags=["flows"])


@router.post("/flows/trigger/{flow_name}")
def trigger_flow(flow_name: str, source_id: str):
    """Trigger a Prefect flow by name with the given source_id parameter."""
    result = prefect_client.trigger_flow(flow_name, source_id)
    return {"message": f"Flow {flow_name} triggered", "result": result}


@router.post("/trigger/{flow_name}", include_in_schema=False)
def trigger_flow_legacy(flow_name: str, source_id: str):
    return trigger_flow(flow_name, source_id)


@router.get("/flows/sources/{source_id}/runs", response_model=List[ScrapeRunSummary])
def list_runs_for_source(source_id: UUID, db: Session = Depends(get_db)):
    runs = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.source_id == source_id)
        .order_by(ScrapeRun.started_at.desc())
        .limit(100)
        .all()
    )
    return runs


@router.get("/flows/runs/{run_id}", response_model=ScrapeRunDetail)
def get_run_detail(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Scrape run not found")

    logs = sorted(run.logs, key=lambda entry: entry.timestamp)
    files = sorted(run.files, key=lambda item: item.processed_at)

    return ScrapeRunDetail(
        id=run.id,
        source_id=run.source_id,
        flow_run_id=run.flow_run_id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_files_found=run.total_files_found,
        total_files_processed=run.total_files_processed,
        notes=run.notes,
        logs=logs,
        files=files,
    )


@router.get("/flows/runs/{run_id}/logs", response_model=List[ScrapeLogEntry])
def get_run_logs(run_id: UUID, db: Session = Depends(get_db)):
    logs = (
        db.query(ScrapeLog)
        .filter(ScrapeLog.run_id == run_id)
        .order_by(ScrapeLog.timestamp.asc())
        .all()
    )
    return logs


@router.get("/flows/runs/{run_id}/files", response_model=List[ScrapedFileResponse])
def get_run_files(run_id: UUID, db: Session = Depends(get_db)):
    files = (
        db.query(ScrapedFile)
        .filter(ScrapedFile.run_id == run_id)
        .order_by(ScrapedFile.processed_at.asc())
        .all()
    )
    return files
