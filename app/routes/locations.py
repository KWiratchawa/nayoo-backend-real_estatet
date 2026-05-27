"""Cascading dropdown: provinces → districts → sub_districts"""
from fastapi import APIRouter, Query
from app.db import get_supabase

router = APIRouter()


@router.get("/provinces")
async def list_provinces():
    """77 จังหวัด"""
    sb = get_supabase()
    res = sb.table("provinces").select("id, name_th").order("name_th").execute()
    return res.data


@router.get("/districts")
async def list_districts(province_id: int = Query(...)):
    """อำเภอในจังหวัด"""
    sb = get_supabase()
    res = (
        sb.table("districts")
        .select("id, name_th, slug")
        .eq("province_id", province_id)
        .order("name_th")
        .execute()
    )
    return res.data


@router.get("/sub_districts")
async def list_sub_districts(district_id: int = Query(...)):
    """ตำบลในอำเภอ"""
    sb = get_supabase()
    res = (
        sb.table("sub_districts")
        .select("id, name_th, is_in_bangkok_metro")
        .eq("district_id", district_id)
        .order("name_th")
        .execute()
    )
    return res.data
