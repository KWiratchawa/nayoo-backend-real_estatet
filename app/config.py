"""Configuration via environment variables"""
import os
from typing import List


class Settings:
    ENV: str = os.getenv("ENV", "production")

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

    # SQLite appraisal database
    APPRAISAL_DB_PATH: str = os.getenv("APPRAISAL_DB_PATH", "./data/appraisal.db")
    APPRAISAL_DB_URL: str = os.getenv("APPRAISAL_DB_URL", "")  # ตอน build จะ download จาก URL นี้

    # CORS
    CORS_ORIGINS: List[str] = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000"
    ).split(",")


settings = Settings()
