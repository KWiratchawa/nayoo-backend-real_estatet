"""
NaYoo Real Estate Backend (v4 — no auth)
========================================
FastAPI + Supabase (user data) + SQLite (appraisal data)
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_sqlite, close_sqlite
from app.routes import health, locations, appraisal, calculations, listings, pdf, users


# ============================================================================
# 🆕 v2.5: CORS Origin Regex
# ----------------------------------------------------------------------------
# รองรับทุก deployment ของ project นี้ (production + Vercel preview branches)
# โดยไม่ต้องมาแก้ env var ทุกครั้งที่ deploy frontend ใหม่
#
# ครอบคลุม:
#   ✅ https://baanprompt-real-estate-tax.vercel.app           (production)
#   ✅ https://baanprompt-real-estate-tax-git-xxx.vercel.app   (preview)
#   ✅ https://baanprompt-real-estate-tax-abc123.vercel.app    (deployment)
#   ✅ https://nayoo-frontend-real-estate.vercel.app           (legacy)
#   ✅ http://localhost:<any port>                              (local dev)
#   ❌ https://anyrandomsite.vercel.app                         (block — secure)
#
# ถ้าต้องการ override (เช่น ใช้ custom domain) → ตั้ง env var:
#   CORS_ORIGIN_REGEX=<your regex>
# ============================================================================
DEFAULT_CORS_ORIGIN_REGEX = (
    r"^("
    r"https://baanprompt-real-estate-tax(-[a-z0-9\-]+)?\.vercel\.app"
    r"|https://nayoo-frontend-real-estate(-[a-z0-9\-]+)?\.vercel\.app"
    r"|http://localhost(:\d+)?"
    r"|http://127\.0\.0\.1(:\d+)?"
    r")$"
)
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 NaYoo API starting — env: {settings.ENV}")
    print(f"   Supabase: {settings.SUPABASE_URL}")
    init_sqlite()
    print(f"   SQLite:   {settings.APPRAISAL_DB_PATH}")
    yield
    close_sqlite()
    print("👋 NaYoo API shutdown")


app = FastAPI(
    title="NaYoo Real Estate API",
    description="ระบบคำนวณค่าใช้จ่ายโอน + ขายฝาก (no auth)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,        # exact match (จาก env)
    allow_origin_regex=CORS_ORIGIN_REGEX,        # 🆕 pattern match (Vercel preview + local)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router, tags=["health"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(locations.router, prefix="/api/locations", tags=["locations"])
app.include_router(appraisal.router, prefix="/api/appraisal", tags=["appraisal"])
app.include_router(calculations.router, prefix="/api/calculations", tags=["calculations"])
app.include_router(listings.router, prefix="/api/listings", tags=["listings"])
app.include_router(pdf.router, prefix="/api/pdf", tags=["pdf"])


@app.get("/")
async def root():
    return {
        "name": "NaYoo Real Estate API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }
