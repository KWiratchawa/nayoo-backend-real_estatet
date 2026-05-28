"""Users CRUD - ไม่ใช้ Supabase Auth (เก็บใน users table ของเรา)"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import get_supabase

router = APIRouter()


class UserCreate(BaseModel):
    user_role: str = Field(..., pattern="^(broker|seller)$")
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., max_length=200)
    phone: str = Field(..., min_length=1, max_length=50)


class UserUpdate(BaseModel):
    user_role: Optional[str] = Field(None, pattern="^(broker|seller)$")
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


@router.post("")
async def create_user(data: UserCreate):
    """สร้าง user ใหม่ — return user_id เพื่อใช้ใน session ปัจจุบัน"""
    sb = get_supabase()
    res = sb.table("users").insert(data.model_dump()).execute()
    if not res.data:
        raise HTTPException(500, "ไม่สามารถสร้างผู้ใช้")
    return res.data[0]


@router.get("/{user_id}")
async def get_user(user_id: str):
    """ดูข้อมูล user — ใช้ตอน load หน้า Edit profile"""
    sb = get_supabase()
    res = sb.table("users").select("*").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบผู้ใช้")
    return res.data[0]


@router.patch("/{user_id}")
async def update_user(user_id: str, data: UserUpdate):
    """แก้ไขข้อมูล user"""
    sb = get_supabase()
    payload = data.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(400, "ไม่มีข้อมูลที่จะอัปเดต")

    res = sb.table("users").update(payload).eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบผู้ใช้")
    return res.data[0]
