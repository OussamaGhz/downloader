"""
API Routes for Telegram Session Management with Interactive OTP Flow
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import uuid

from app.core.database import get_db
from app.models.session import TelegramSession
from app.models.temp_session import TempSession
from app.schemas.session import (
    OTPSendRequest,
    OTPSendResponse,
    OTPVerifyRequest,
    SessionFileUploadResponse,
    SessionFinalizeRequest,
    SessionResponse,
    ChannelInfo,
    SessionUpdate,
)
from app.services.encryption import encrypt_data, decrypt_data
from app.services.telegram_client import TelegramClientService


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/send-otp", response_model=OTPSendResponse)
async def send_otp(request: OTPSendRequest, db: Session = Depends(get_db)):
    """
    Step 1: Send OTP to phone number

    Frontend workflow:
    1. User enters phone_number, api_id, api_hash
    2. Backend sends OTP via Telegram
    3. Backend returns temp_session_id
    4. Frontend asks user for OTP code
    5. Frontend calls /verify-otp with code
    """
    # Check if phone number already has an active session
    existing = (
        db.query(TelegramSession)
        .filter(TelegramSession.phone_number == request.phone_number)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Session already exists for {request.phone_number}. Delete it first or use existing session.",
        )

    try:
        # Send OTP via Telethon
        session_string, phone_code_hash = await TelegramClientService.send_otp(
            api_id=request.api_id,
            api_hash=request.api_hash,
            phone_number=request.phone_number,
        )

        # Create temporary session
        temp_session = TempSession(
            id=str(uuid.uuid4()),
            phone_number=request.phone_number,
            api_id=request.api_id,
            api_hash=encrypt_data(request.api_hash),
            session_string=encrypt_data(session_string),
            phone_code_hash=encrypt_data(phone_code_hash),
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )

        db.add(temp_session)
        db.commit()
        db.refresh(temp_session)

        return OTPSendResponse(
            temp_session_id=temp_session.id,
            phone_number=request.phone_number,
            message="OTP sent to your Telegram app. Enter the code to continue.",
            expires_in_minutes=10,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {str(e)}")


@router.post("/verify-otp", response_model=SessionResponse)
async def verify_otp(request: OTPVerifyRequest, db: Session = Depends(get_db)):
    """
    Step 2: Verify OTP and create permanent session

    Frontend workflow:
    1. User enters OTP code (and 2FA password if prompted)
    2. Backend verifies code with Telegram
    3. Backend creates permanent session
    4. Returns session details
    """
    # Get temporary session
    temp_session = (
        db.query(TempSession).filter(TempSession.id == request.temp_session_id).first()
    )

    if not temp_session:
        raise HTTPException(
            status_code=404, detail="Temporary session not found or expired"
        )

    # Check if expired
    if temp_session.is_expired:
        db.delete(temp_session)
        db.commit()
        raise HTTPException(
            status_code=400, detail="Temporary session expired. Request a new OTP."
        )

    # Decrypt temporary data
    api_hash = decrypt_data(temp_session.api_hash)
    session_string = decrypt_data(temp_session.session_string)
    phone_code_hash = decrypt_data(temp_session.phone_code_hash)

    try:
        # Verify OTP with Telegram
        final_session_string = await TelegramClientService.verify_otp(
            api_id=temp_session.api_id,
            api_hash=api_hash,
            phone_number=temp_session.phone_number,
            code=request.code,
            phone_code_hash=phone_code_hash,
            session_string=session_string,
            password=request.password,
        )

        # Create permanent session
        session_name = request.session_name or f"Session {temp_session.phone_number}"

        permanent_session = TelegramSession(
            id=str(uuid.uuid4()),
            name=session_name,
            phone_number=temp_session.phone_number,
            api_id=temp_session.api_id,
            api_hash=encrypt_data(api_hash),
            session_string=encrypt_data(final_session_string),
            is_active="active",
        )

        db.add(permanent_session)

        # Delete temporary session
        db.delete(temp_session)

        db.commit()
        db.refresh(permanent_session)

        return permanent_session

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to verify OTP: {str(e)}")


@router.post("/upload-file", response_model=SessionFileUploadResponse)
async def upload_session_file(
    api_id: int = Form(...),
    api_hash: str = Form(...),
    session_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Alternative: Upload existing .session file

    Frontend workflow:
    1. User selects .session file from their computer
    2. User provides api_id and api_hash
    3. Backend converts file to StringSession
    4. Backend extracts phone number
    5. Frontend calls /finalize with name
    """
    if not session_file.filename.endswith(".session"):
        raise HTTPException(status_code=400, detail="File must be a .session file")

    try:
        # Read file content
        file_content = await session_file.read()

        # Convert to string session
        session_string, phone_number = (
            await TelegramClientService.convert_session_file_to_string(
                session_file_content=file_content, api_id=api_id, api_hash=api_hash
            )
        )

        # Check if phone already exists
        existing = (
            db.query(TelegramSession)
            .filter(TelegramSession.phone_number == phone_number)
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400, detail=f"Session already exists for {phone_number}"
            )

        # Create temporary session for finalization
        temp_session = TempSession(
            id=str(uuid.uuid4()),
            phone_number=phone_number,
            api_id=api_id,
            api_hash=encrypt_data(api_hash),
            session_string=encrypt_data(session_string),
            phone_code_hash=encrypt_data("FILE_UPLOAD"),  # Marker for file uploads
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        db.add(temp_session)
        db.commit()
        db.refresh(temp_session)

        return SessionFileUploadResponse(
            temp_session_id=temp_session.id,
            phone_number=phone_number,
            message=f"Session file uploaded for {phone_number}. Provide a name to save.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to upload session file: {str(e)}"
        )


@router.post("/finalize", response_model=SessionResponse)
async def finalize_session(
    request: SessionFinalizeRequest, db: Session = Depends(get_db)
):
    """
    Step 3: Finalize session creation with a name

    Used after uploading a session file to provide a friendly name
    """
    # Get temporary session
    temp_session = (
        db.query(TempSession).filter(TempSession.id == request.temp_session_id).first()
    )

    if not temp_session:
        raise HTTPException(status_code=404, detail="Temporary session not found")

    if temp_session.is_expired:
        db.delete(temp_session)
        db.commit()
        raise HTTPException(status_code=400, detail="Temporary session expired")

    # Decrypt data
    api_hash = decrypt_data(temp_session.api_hash)
    session_string = decrypt_data(temp_session.session_string)

    # Create permanent session
    permanent_session = TelegramSession(
        id=str(uuid.uuid4()),
        name=request.name,
        phone_number=temp_session.phone_number,
        api_id=temp_session.api_id,
        api_hash=encrypt_data(api_hash),
        session_string=encrypt_data(session_string),
        is_active="active",
    )

    db.add(permanent_session)
    db.delete(temp_session)
    db.commit()
    db.refresh(permanent_session)

    return permanent_session


@router.get("/", response_model=List[SessionResponse])
def get_all_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get all stored Telegram sessions"""
    sessions = db.query(TelegramSession).offset(skip).limit(limit).all()
    return sessions


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    """Get details of a specific session"""
    session = db.query(TelegramSession).filter(TelegramSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.get("/{session_id}/channels", response_model=List[ChannelInfo])
async def get_session_channels(session_id: str, db: Session = Depends(get_db)):
    """
    Get all channels/groups accessible by this session
    """
    session = db.query(TelegramSession).filter(TelegramSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.is_active != "active":
        raise HTTPException(status_code=400, detail="Session is not active")

    # Decrypt credentials
    api_hash = decrypt_data(session.api_hash)
    session_string = decrypt_data(session.session_string)

    # Fetch channels using TelegramClientService
    try:
        channels = await TelegramClientService.get_user_channels(
            api_id=session.api_id, api_hash=api_hash, session_string=session_string
        )
        return channels
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch channels: {str(e)}"
        )


@router.post("/{session_id}/test")
async def test_session(session_id: str, db: Session = Depends(get_db)):
    """Test if a session is still valid and authorized"""
    session = db.query(TelegramSession).filter(TelegramSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Decrypt credentials
    api_hash = decrypt_data(session.api_hash)
    session_string = decrypt_data(session.session_string)

    # Test session
    try:
        is_valid = await TelegramClientService.test_session(
            api_id=session.api_id, api_hash=api_hash, session_string=session_string
        )

        # Update session status
        if not is_valid:
            session.is_active = "expired"
            db.commit()

        return {
            "session_id": session_id,
            "is_valid": is_valid,
            "status": session.is_active,
        }
    except Exception as e:
        return {"session_id": session_id, "is_valid": False, "error": str(e)}


@router.put("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str, session_update: SessionUpdate, db: Session = Depends(get_db)
):
    """Update session details (name, active status)"""
    session = db.query(TelegramSession).filter(TelegramSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session_update.name is not None:
        session.name = session_update.name

    if session_update.is_active is not None:
        session.is_active = session_update.is_active

    db.commit()
    db.refresh(session)

    return session


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a session"""
    session = db.query(TelegramSession).filter(TelegramSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if any sources are using this session
    if session.sources:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete session. It is being used by {len(session.sources)} source(s)",
        )

    db.delete(session)
    db.commit()

    return {"message": "Session deleted successfully", "id": session_id}


@router.delete("/temp/{temp_session_id}")
def cancel_temp_session(temp_session_id: str, db: Session = Depends(get_db)):
    """Cancel a temporary session (useful if user abandons OTP flow)"""
    temp_session = (
        db.query(TempSession).filter(TempSession.id == temp_session_id).first()
    )

    if not temp_session:
        raise HTTPException(status_code=404, detail="Temporary session not found")

    db.delete(temp_session)
    db.commit()

    return {"message": "Temporary session cancelled", "id": temp_session_id}
