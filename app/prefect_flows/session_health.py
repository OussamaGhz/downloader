"""Prefect flow to validate stored Telegram sessions and update their status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from prefect import flow, get_run_logger, task

from app.core.database import SessionLocal
from app.models.session import TelegramSession
from app.services.encryption import decrypt_data
from app.services.telegram_client import TelegramClientService


@task
def fetch_sessions() -> List[Dict[str, Any]]:
    """Load all Telegram sessions from the database."""
    with SessionLocal() as db:
        sessions = db.query(TelegramSession).all()
        return [
            {
                "id": session.id,
                "api_id": session.api_id,
                "api_hash": session.api_hash,
                "session_string": session.session_string,
                "current_status": session.is_active,
            }
            for session in sessions
        ]


@task
async def validate_session(session_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single Telegram session and return its updated status."""
    logger = get_run_logger()
    session_id = session_payload["id"]

    try:
        api_hash = decrypt_data(session_payload["api_hash"])
        session_string = decrypt_data(session_payload["session_string"])
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "Failed to decrypt session credentials for %s: %s",
            session_id,
            exc,
        )
        return {"id": session_id, "is_valid": False, "error": str(exc)}

    try:
        is_valid = await TelegramClientService.test_session(
            api_id=session_payload["api_id"],
            api_hash=api_hash,
            session_string=session_string,
        )
        return {"id": session_id, "is_valid": bool(is_valid)}
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Session validation failed for %s: %s", session_id, exc)
        return {"id": session_id, "is_valid": False, "error": str(exc)}


@task
def persist_results(results: List[Dict[str, Any]]):
    """Persist validation results back to the database."""
    logger = get_run_logger()
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        for result in results:
            session = (
                db.query(TelegramSession)
                .filter(TelegramSession.id == result["id"])
                .first()
            )
            if not session:
                logger.warning("Session %s not found during persistence", result["id"])
                continue

            session.is_active = "active" if result.get("is_valid") else "expired"
            session.last_checked_at = now

            if not result.get("is_valid") and result.get("error"):
                logger.info(
                    "Session %s marked inactive due to error: %s",
                    session.id,
                    result["error"],
                )

        db.commit()


@flow(name="session-health-check")
def session_health_check_flow() -> List[Dict[str, Any]]:
    """Prefect flow entry point for session health validation."""
    logger = get_run_logger()
    payload_future = fetch_sessions()
    session_payloads = payload_future.result()

    if not session_payloads:
        logger.info("No Telegram sessions found for validation.")
        return []

    validation_futures = [
        validate_session.submit(payload) for payload in session_payloads
    ]
    validation_results = [future.result() for future in validation_futures]

    persist_future = persist_results.submit(validation_results)
    persist_future.result()

    summary = {
        "total": len(validation_results),
        "active": sum(1 for item in validation_results if item.get("is_valid")),
        "inactive": sum(1 for item in validation_results if not item.get("is_valid")),
    }
    logger.info(
        "Session health check complete: %s active / %s inactive (total %s)",
        summary["active"],
        summary["inactive"],
        summary["total"],
    )
    return validation_results
