"""Database clients: Supabase (user data) + SQLite (appraisal)"""
import sqlite3
from pathlib import Path
from typing import Optional

from supabase import create_client, Client
from app.config import settings


# ===== Supabase =====

def get_supabase() -> Client:
    """Service role client - full DB access"""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


# ===== SQLite (read-only appraisal data) =====

_sqlite_conn: Optional[sqlite3.Connection] = None


def init_sqlite():
    """เรียกตอน startup - เปิด SQLite connection"""
    global _sqlite_conn
    db_path = Path(settings.APPRAISAL_DB_PATH)
    if not db_path.exists():
        raise RuntimeError(
            f"❌ appraisal.db ไม่พบที่ {db_path}\n"
            f"   ตอน build ต้อง download จาก {settings.APPRAISAL_DB_URL}\n"
            f"   หรือ run: python scripts/download_appraisal.py"
        )

    # Open read-only เพื่อความปลอดภัย
    uri = f"file:{db_path}?mode=ro"
    _sqlite_conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    _sqlite_conn.row_factory = sqlite3.Row  # query → dict-like


def close_sqlite():
    global _sqlite_conn
    if _sqlite_conn:
        _sqlite_conn.close()
        _sqlite_conn = None


def get_sqlite() -> sqlite3.Connection:
    """ใช้ใน routes — return shared connection"""
    if _sqlite_conn is None:
        raise RuntimeError("SQLite not initialized — call init_sqlite() first")
    return _sqlite_conn


def query_sqlite(sql: str, params: tuple = ()) -> list:
    """Helper: run SELECT → return list of dicts"""
    conn = get_sqlite()
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]
