"""Supabase JWT auth dependency"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import get_supabase

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Verify Supabase JWT → return user info"""
    token = credentials.credentials

    if not settings.SUPABASE_JWT_SECRET:
        payload = jwt.decode(token, options={"verify_signature": False})
    else:
        try:
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
            )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user ID")

    return {"auth_user_id": user_id, "email": payload.get("email")}


async def get_current_agent(user: dict = Depends(get_current_user)) -> dict:
    """Get agent profile"""
    sb = get_supabase()
    res = sb.table("agents").select("*").eq("auth_user_id", user["auth_user_id"]).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return res.data[0]
