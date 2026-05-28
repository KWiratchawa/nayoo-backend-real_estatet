"""Health check - UptimeRobot ping target (รองรับทั้ง GET + HEAD)"""
from fastapi import APIRouter, Response
from app.db import get_sqlite

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health(response: Response):
    """Public health check - รองรับ HEAD (UptimeRobot ใช้ HEAD)"""
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