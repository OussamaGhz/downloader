"""
Background cleanup service for expired temporary sessions
"""

import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.temp_session import TempSession


async def cleanup_expired_temp_sessions():
    """
    Periodically delete expired temporary sessions from database
    Runs every 5 minutes
    """
    while True:
        try:
            db: Session = SessionLocal()

            # Delete expired temporary sessions
            deleted_count = (
                db.query(TempSession)
                .filter(TempSession.expires_at < datetime.utcnow())
                .delete()
            )

            db.commit()

            if deleted_count > 0:
                print(f"[Cleanup] Deleted {deleted_count} expired temporary session(s)")

            db.close()

        except Exception as e:
            print(f"[Cleanup] Error during cleanup: {e}")

        # Wait 5 minutes before next cleanup
        await asyncio.sleep(300)
