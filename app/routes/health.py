"""Health check - UptimeRobot ping target (รองรับทั้ง GET + HEAD)"""
from fastapi import APIRouter, Response
from app.db import get_sqlite

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health(response: Response):
    """
    Public health check.
    รองรับ HEAD (UptimeRobot free plan ใช้ HEAD เป็น default)
    """
    sqlite_ok = False
    try:
        get_sqlite().execute("SELECT 1").fetchone()
        sqlite_ok = True
    except Exception:
        pass

    if not sqlite_ok:
        # ยัง return 200 แต่บอก degraded — กัน UptimeRobot false alarm
        # (ถ้าอยากให้ alert จริงตอน sqlite ล่ม เปลี่ยนเป็น 503)
        response.status_code = 200

    return {
        "status": "ok" if sqlite_ok else "degraded",
        "service": "nayoo-api",
        "sqlite": sqlite_ok,
    }
