"""
API Routes for Source Management (Private and Public Channels)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import uuid

from app.core.database import get_db
from app.models.source import Source as SourceModel, AccessLevelEnum
from app.models.session import TelegramSession
from app.schemas.source import (
    SourceCreatePrivate,
    SourceCreatePublic,
    SourceResponse,
    SourceUpdate,
)
from app.services.encryption import encrypt_data, decrypt_data
from app.services.prefect_client import prefect_client

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("/private", response_model=SourceResponse)
def create_private_source(source: SourceCreatePrivate, db: Session = Depends(get_db)):
    """
    Create a source for a PRIVATE channel using an existing session

    Workflow:
    1. User selects an existing session
    2. User fetches channels via GET /sessions/{id}/channels
    3. User selects a channel and provides details
    4. This endpoint creates the source with session reference
    """
    # Verify session exists and is active
    session = (
        db.query(TelegramSession)
        .filter(TelegramSession.id == source.session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.is_active != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    # Create source
    new_source = SourceModel(
        id=uuid.uuid4(),
        name=source.name,
        api_id=encrypt_data(str(source.api_id)),
        api_hash=encrypt_data(source.api_hash),
        access_level=AccessLevelEnum.PRIVATE,
        identifier=str(source.channel_id),
        channel_title=source.channel_title,
        session_id=source.session_id,
        file_types=source.file_types,
        target=source.target,
        target_path=source.target_path,
        schedule=source.schedule,
        is_active="active",
    )

    db.add(new_source)
    db.commit()
    db.refresh(new_source)

    # Create Prefect deployment
    if source.schedule:
        try:
            prefect_client.create_deployment(
                source_id=str(new_source.id),
                source_name=new_source.name,
                cron_schedule=source.schedule,
            )
        except Exception as e:
            print(f"Warning: Failed to create Prefect deployment: {e}")

    return new_source


@router.post("/public", response_model=SourceResponse)
def create_public_source(source: SourceCreatePublic, db: Session = Depends(get_db)):
    """
    Create a source for a PUBLIC channel

    Uses a shared read-only session (stored once) or bot token for accessing public channels.
    User provides channel username/ID and configuration.
    """
    new_source = SourceModel(
        id=uuid.uuid4(),
        name=source.name,
        api_id=encrypt_data(str(source.api_id)),
        api_hash=encrypt_data(source.api_hash),
        access_level=AccessLevelEnum.PUBLIC,
        identifier=source.channel_username,
        bot_token=encrypt_data(source.bot_token) if source.bot_token else None,
        file_types=source.file_types,
        target=source.target,
        target_path=source.target_path,
        schedule=source.schedule,
        is_active="active",
    )

    db.add(new_source)
    db.commit()
    db.refresh(new_source)

    # Create Prefect deployment
    if source.schedule:
        try:
            prefect_client.create_deployment(
                source_id=str(new_source.id),
                source_name=new_source.name,
                cron_schedule=source.schedule,
            )
        except Exception as e:
            print(f"Warning: Failed to create Prefect deployment: {e}")

    return new_source


@router.get("/", response_model=List[SourceResponse])
def read_sources(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all sources"""
    sources = db.query(SourceModel).offset(skip).limit(limit).all()
    return sources


@router.get("/{source_id}", response_model=SourceResponse)
def read_source(source_id: UUID, db: Session = Depends(get_db)):
    """Get a specific source"""
    db_source = db.query(SourceModel).filter(SourceModel.id == source_id).first()
    if db_source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return db_source


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(source_id: UUID, source: SourceUpdate, db: Session = Depends(get_db)):
    """Update a source"""
    db_source = db.query(SourceModel).filter(SourceModel.id == source_id).first()
    if db_source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    # Update fields
    if source.name:
        db_source.name = source.name
    if source.schedule is not None:
        db_source.schedule = source.schedule
    if source.file_types:
        db_source.file_types = source.file_types
    if source.target_path is not None:
        db_source.target_path = source.target_path
    if source.is_active:
        db_source.is_active = source.is_active

    db.commit()
    db.refresh(db_source)

    # Update Prefect deployment with new schedule
    if source.schedule is not None:
        try:
            prefect_client.update_deployment(
                source_id=str(db_source.id),
                source_name=db_source.name,
                cron_schedule=db_source.schedule,
            )
        except Exception as e:
            print(f"Warning: Failed to update Prefect deployment: {e}")

    return db_source


@router.delete("/{source_id}")
def delete_source(source_id: UUID, db: Session = Depends(get_db)):
    """Delete a source and its Prefect deployment"""
    db_source = db.query(SourceModel).filter(SourceModel.id == source_id).first()
    if db_source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    # Delete Prefect deployment first
    try:
        prefect_client.delete_deployment(str(source_id))
    except Exception as e:
        print(f"Warning: Failed to delete Prefect deployment: {e}")

    # Delete source from database
    db.delete(db_source)
    db.commit()

    return {"message": f"Source {source_id} deleted successfully"}


@router.post("/{source_id}/trigger")
def trigger_source_flow(source_id: UUID, db: Session = Depends(get_db)):
    """Manually trigger a source scraping job"""
    db_source = db.query(SourceModel).filter(SourceModel.id == source_id).first()
    if db_source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    # Trigger the Prefect flow using the deployment name
    deployment_name = f"source-{source_id}"
    try:
        result = prefect_client.trigger_flow(deployment_name, str(source_id))
        return {"message": f"Triggered flow for source {source_id}", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger flow: {str(e)}")
