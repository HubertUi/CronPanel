"""Health check endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.database.database import engine
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    timestamp: str
    database: str


def _check_database() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health must never raise to the client
        return False


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    database_ok = _check_database()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        database="ok" if database_ok else "error",
    )
