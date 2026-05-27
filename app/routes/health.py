"""Health check - UptimeRobot ping target"""
from fastapi import APIRouter
from app.db import get_sqlite

router = APIRouter()


@router.get("/health")
async def health():
    """Public health check"""
    sqlite_ok = False
    try:
        get_sqlite().execute("SELECT 1").fetchone()
        sqlite_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if sqlite_ok else "degraded",
        "service": "nayoo-api",
        "sqlite": sqlite_ok,
    }
