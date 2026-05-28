"""
NaYoo Real Estate Backend (v4 — no auth)
========================================
FastAPI + Supabase (user data) + SQLite (appraisal data)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_sqlite, close_sqlite
from app.routes import health, locations, appraisal, calculations, listings, pdf, users


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
    allow_origins=settings.CORS_ORIGINS,
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
