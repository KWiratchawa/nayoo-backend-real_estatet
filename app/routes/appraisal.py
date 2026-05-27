"""
Appraisal lookup — query SQLite (read-only)

4 paths:
  /land_deed       → ค้นจากเลขโฉนด/เลขที่ดิน (โดย district_id)
  /land_unit/*     → สรุปราคาที่ดินตามถนน (raw text dropdowns)
  /condo/*         → ห้องชุดรายชั้น
  /building_types  → 69 ประเภทสิ่งปลูกสร้าง
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.db import query_sqlite, get_supabase

router = APIRouter()


# =============================================================================
# Path A: ที่ดินรายโฉนด (เลขโฉนด / เลขที่ดิน)
# =============================================================================

@router.get("/land_deed")
async def lookup_land_deed(
    province_id: int = Query(...),
    district_id: int = Query(...),
    deed_no: Optional[str] = Query(None, description="เลขโฉนด"),
    land_no: Optional[str] = Query(None, description="เลขที่ดิน"),
):
    """Lookup ราคาประเมินจาก เลขโฉนด / เลขที่ดิน"""
    if not deed_no and not land_no:
        raise HTTPException(400, "ต้องระบุ deed_no หรือ land_no")

    sql = """
        SELECT * FROM land_deed
        WHERE province_id = ? AND district_id = ?
    """
    params = [province_id, district_id]

    if deed_no:
        sql += " AND title_deed_no = ?"
        params.append(deed_no.strip())
    if land_no:
        sql += " AND land_no = ?"
        params.append(land_no.strip())

    sql += " LIMIT 10"
    results = query_sqlite(sql, tuple(params))

    if not results:
        raise HTTPException(404, "ไม่พบราคาประเมิน — ตรวจสอบเลขโฉนด/เลขที่ดิน/อำเภอ")
    return results


# =============================================================================
# Path B: สรุปราคาประเมินที่ดิน (raw text dropdowns)
# =============================================================================

@router.get("/land_unit/provinces")
async def land_unit_provinces():
    """Distinct จังหวัดใน land_unit (สำหรับ dropdown)"""
    return query_sqlite("""
        SELECT DISTINCT province_text AS name
        FROM land_unit
        ORDER BY province_text
    """)


@router.get("/land_unit/districts")
async def land_unit_districts(province: str = Query(..., description="ชื่อจังหวัด")):
    """Distinct อำเภอภายใต้จังหวัด"""
    return query_sqlite("""
        SELECT DISTINCT district_text AS name
        FROM land_unit
        WHERE province_text = ?
        ORDER BY district_text
    """, (province,))


@router.get("/land_unit/branches")
async def land_unit_branches(
    province: str = Query(...),
    district: Optional[str] = Query(None),
):
    """Distinct สำนักงานสาขา"""
    sql = """
        SELECT DISTINCT land_office_branch AS name
        FROM land_unit
        WHERE province_text = ?
          AND land_office_branch IS NOT NULL
    """
    params = [province]
    if district:
        sql += " AND district_text = ?"
        params.append(district)
    sql += " ORDER BY land_office_branch"
    return query_sqlite(sql, tuple(params))


@router.get("/land_unit/search")
async def land_unit_search(
    province: str = Query(...),
    district: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    q: str = Query("", description="คำค้นใน ชื่อหน่วยที่ดิน"),
    limit: int = Query(50, ge=1, le=200),
):
    """ค้นหาราคาประเมินที่ดิน — filter ด้วย dropdown values"""
    sql = """
        SELECT id, unit_seq, unit_name,
               price_min_per_sqwah, price_max_per_sqwah,
               price_min_per_sqm, price_max_per_sqm,
               province_text, district_text, land_office_branch,
               data_type, accounting_period
        FROM land_unit
        WHERE province_text = ?
    """
    params = [province]

    if district:
        sql += " AND district_text = ?"
        params.append(district)
    if branch:
        sql += " AND land_office_branch = ?"
        params.append(branch)
    if q.strip():
        sql += " AND unit_name LIKE ?"
        params.append(f"%{q.strip()}%")

    sql += " ORDER BY unit_seq LIMIT ?"
    params.append(limit)

    return query_sqlite(sql, tuple(params))


# =============================================================================
# Path C: ห้องชุด
# =============================================================================

@router.get("/condo/search")
async def condo_search(
    province_id: int = Query(...),
    q: str = Query("", description="ชื่ออาคารชุด"),
    limit: int = Query(30, ge=1, le=100),
):
    """ค้นหาอาคารชุด — return unique building names"""
    sql = """
        SELECT DISTINCT building_name
        FROM condo
        WHERE province_id = ?
    """
    params = [province_id]
    if q.strip():
        sql += " AND building_name_normalized LIKE ?"
        params.append(f"%{q.strip().lower()}%")
    sql += " ORDER BY building_name LIMIT ?"
    params.append(limit)
    return query_sqlite(sql, tuple(params))


@router.get("/condo/floors")
async def condo_floors(
    province_id: int = Query(...),
    building_name: str = Query(...),
):
    """ดูชั้น + ราคา/ตร.ม. ของอาคารชุด"""
    results = query_sqlite("""
        SELECT id, floor_no, floor_no_numeric, unit_type, price_per_sqm
        FROM condo
        WHERE province_id = ? AND building_name = ?
        ORDER BY floor_no_numeric
    """, (province_id, building_name))

    if not results:
        raise HTTPException(404, f"ไม่พบข้อมูลอาคารชุด: {building_name}")
    return results


# =============================================================================
# Path D: สิ่งปลูกสร้าง
# =============================================================================

@router.get("/building_types")
async def list_building_types(province_id: int = Query(...)):
    """69 ประเภทสิ่งปลูกสร้าง + ราคา/ตร.ม."""
    return query_sqlite("""
        SELECT id, type_code, type_name, type_group, price_per_sqm, remark
        FROM building_type
        WHERE province_id = ?
        ORDER BY type_code
    """, (province_id,))
