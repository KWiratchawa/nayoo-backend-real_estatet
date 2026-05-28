"""Listings CRUD - via Supabase RLS"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import get_current_agent
from app.db import get_supabase

router = APIRouter()


class ListingCreate(BaseModel):
    workflow_type: str

    # Location
    province_id: Optional[int] = None
    district_id: Optional[int] = None
    sub_district_id: Optional[int] = None
    postal_code: Optional[str] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None

    # Seller
    seller_type: str
    acquisition_type: str
    acquisition_subtype: Optional[str] = None
    is_in_bangkok_metro: bool = False
    acquisition_year: int
    sale_year: int
    years_in_household_registration: int = 0
    has_intent_to_trade: bool = False

    # Property
    property_type: str
    land_doc_type: Optional[str] = None
    title_deed_no: Optional[str] = None
    land_no: Optional[str] = None
    rawang_code: Optional[str] = None
    land_rai: int = 0
    land_ngan: int = 0
    land_sq_wah: float = 0
    land_total_sq_wah: Optional[float] = None
    condo_building_name: Optional[str] = None
    condo_floor: Optional[str] = None
    condo_floor_area_sqm: Optional[float] = None
    building_type_code: Optional[str] = None
    building_floor_area_sqm: Optional[float] = None

    # Prices
    sale_price: float
    appraisal_price_total: float
    appraisal_land_price: Optional[float] = None
    appraisal_building_price: Optional[float] = None
    appraisal_condo_price: Optional[float] = None
    appraisal_source_detail: Optional[dict] = None

    # Mortgage
    has_mortgage: bool = False
    mortgage_amount: Optional[float] = None

    # WF2 specific
    expected_market_price: Optional[float] = None
    interest_rate_monthly: Optional[float] = None
    total_term_months: Optional[int] = None
    outstanding_debts: float = 0
    transfer_cost_paid_by: Optional[str] = None

    notes: Optional[str] = None


@router.post("")
async def create_listing(
    data: ListingCreate,
    agent: dict = Depends(get_current_agent),
):
    """สร้าง listing — auto-generate listing_no"""
    sb = get_supabase()
    payload = data.model_dump(exclude_none=True)
    payload["agent_id"] = agent["id"]
    payload["status"] = "submitted"

    res = sb.table("listings").insert(payload).execute()
    if not res.data:
        raise HTTPException(500, "ไม่สามารถสร้าง listing")
    return res.data[0]


@router.get("")
async def list_my_listings(
    agent: dict = Depends(get_current_agent),
    workflow_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """ดู listings ของตัวเอง"""
    sb = get_supabase()
    q = (
        sb.table("listings")
        .select("*")
        .eq("agent_id", agent["id"])
        .order("created_at", desc=True)
        .limit(limit)
    )
    if workflow_type:
        q = q.eq("workflow_type", workflow_type)
    if status:
        q = q.eq("status", status)
    return q.execute().data


@router.get("/{listing_id}")
async def get_listing(
    listing_id: str,
    agent: dict = Depends(get_current_agent),
):
    """ดู listing + calc ล่าสุด"""
    sb = get_supabase()
    res = sb.table("listings").select("*").eq("id", listing_id).eq("agent_id", agent["id"]).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบ listing")
    listing = res.data[0]

    calc = (
        sb.table("calculations")
        .select("*")
        .eq("listing_id", listing_id)
        .order("calculated_at", desc=True)
        .limit(1)
        .execute()
    )
    listing["latest_calculation"] = calc.data[0] if calc.data else None
    return listing


@router.post("/{listing_id}/calculations")
async def save_calculation(
    listing_id: str,
    calc_data: dict,
    agent: dict = Depends(get_current_agent),
):
    """บันทึก calculation"""
    sb = get_supabase()
    res = sb.table("listings").select("id").eq("id", listing_id).eq("agent_id", agent["id"]).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบ listing")

    calc_data["listing_id"] = listing_id
    calc_data.setdefault("engine_version", "1.0.0")

    insert_res = sb.table("calculations").insert(calc_data).execute()
    sb.table("listings").update({"status": "calculated"}).eq("id", listing_id).execute()

    return insert_res.data[0] if insert_res.data else {}
