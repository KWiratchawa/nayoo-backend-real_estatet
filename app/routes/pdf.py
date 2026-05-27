"""PDF report generation - WeasyPrint"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.auth import get_current_agent
from app.db import get_supabase

router = APIRouter()


def format_thai_baht(amount) -> str:
    if amount is None:
        return "-"
    try:
        return f"{float(amount):,.2f}"
    except (ValueError, TypeError):
        return "-"


def render_pdf_html(listing: dict, calc: dict) -> str:
    workflow = calc.get("calculation_type", "transfer")
    today = datetime.now().strftime("%d/%m/%Y")
    listing_no = listing.get("listing_no", "N/A")
    title = "ค่าใช้จ่ายขายฝาก" if workflow == "leaseback" else "ค่าใช้จ่ายวันโอน"

    line_items = calc.get("line_items", [])
    items_html = ""
    for it in line_items:
        items_html += f"""
        <tr>
            <td>{it.get('description', '')}</td>
            <td class="formula">{it.get('formula', '')}</td>
            <td class="amount">{format_thai_baht(it.get('amount'))}</td>
        </tr>"""

    wf2_section = ""
    if workflow == "leaseback":
        wf2_section = f"""
        <h3>ยอดกำหนดสินไถ่</h3>
        <table>
            <tr><td>ราคาคาดว่าขายออก</td><td class="amount">{format_thai_baht(listing.get('expected_market_price'))}</td></tr>
            <tr><td>ราคาขายฝากที่ตกลง</td><td class="amount">{format_thai_baht(listing.get('sale_price'))}</td></tr>
            <tr><td>หัก ดอกเบี้ยล่วงหน้า</td><td class="amount">- {format_thai_baht(calc.get('advance_interest_amount'))}</td></tr>
            <tr><td>หัก ค่าปากถุง 5%</td><td class="amount">- {format_thai_baht(calc.get('mouth_money_fee'))}</td></tr>
            <tr class="total"><td>เหลือเงิน</td><td class="amount">{format_thai_baht(calc.get('remaining_cash'))}</td></tr>
            <tr class="total"><td>ยอดกำหนดสินไถ่</td><td class="amount">{format_thai_baht(calc.get('redemption_amount'))}</td></tr>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <title>{title} - {listing_no}</title>
    <style>
        @page {{ size: A4; margin: 1.5cm; }}
        body {{ font-family: 'Sarabun', sans-serif; font-size: 11pt; }}
        .header {{ text-align: center; border-bottom: 2px solid #1e3a8a; padding-bottom: 10px; margin-bottom: 20px; }}
        .header h1 {{ margin: 5px 0; color: #1e3a8a; }}
        .meta {{ display: flex; justify-content: space-between; margin-bottom: 15px; font-size: 10pt; color: #555; }}
        h3 {{ background: #f3f4f6; padding: 8px; border-left: 4px solid #1e3a8a; margin-top: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
        td, th {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }}
        .amount {{ text-align: right; font-family: monospace; }}
        .formula {{ font-size: 9pt; color: #6b7280; }}
        .total {{ background: #fef3c7; font-weight: bold; }}
        .footer {{ margin-top: 30px; font-size: 9pt; color: #9ca3af; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div>NaYoo Real Estate System</div>
    </div>
    <div class="meta">
        <div>Listing: <strong>{listing_no}</strong></div>
        <div>วันที่: {today}</div>
    </div>
    <h3>ข้อมูลทรัพย์</h3>
    <table>
        <tr><td>ประเภททรัพย์</td><td>{listing.get('property_type', '-')}</td></tr>
        <tr><td>ผู้ขาย</td><td>{listing.get('seller_type', '-')} ({listing.get('acquisition_type', '-')})</td></tr>
        <tr><td>ราคาขาย</td><td class="amount">{format_thai_baht(listing.get('sale_price'))}</td></tr>
        <tr><td>ราคาประเมิน</td><td class="amount">{format_thai_baht(listing.get('appraisal_price_total'))}</td></tr>
        <tr><td><strong>Tax Base (MAX)</strong></td><td class="amount"><strong>{format_thai_baht(calc.get('tax_base'))}</strong></td></tr>
    </table>
    {wf2_section}
    <h3>รายละเอียดค่าใช้จ่าย</h3>
    <table>
        <thead>
            <tr style="background: #1e3a8a; color: white;">
                <th style="text-align: left;">รายการ</th>
                <th style="text-align: left;">สูตร</th>
                <th style="text-align: right;">จำนวน (บาท)</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
            <tr class="total">
                <td colspan="2">รวมค่าใช้จ่ายทั้งหมด</td>
                <td class="amount">{format_thai_baht(calc.get('total_cost'))}</td>
            </tr>
        </tbody>
    </table>
    <div class="footer">
        เอกสารนี้สร้างโดยระบบ NaYoo Real Estate — เพื่อประมาณการค่าใช้จ่ายเบื้องต้น<br>
        ตัวเลขสุดท้ายต้องยืนยันที่สำนักงานที่ดิน
    </div>
</body>
</html>"""


@router.get("/{listing_id}/generate")
async def generate_pdf(
    listing_id: str,
    agent: dict = Depends(get_current_agent),
):
    """Generate PDF + download"""
    sb = get_supabase()
    res = sb.table("listings").select("*").eq("id", listing_id).eq("agent_id", agent["id"]).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบ listing")
    listing = res.data[0]

    calc_res = (
        sb.table("calculations")
        .select("*")
        .eq("listing_id", listing_id)
        .order("calculated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not calc_res.data:
        raise HTTPException(400, "ยังไม่มี calculation")
    calc = calc_res.data[0]

    try:
        from weasyprint import HTML
    except ImportError:
        raise HTTPException(500, "WeasyPrint not installed")

    html_str = render_pdf_html(listing, calc)
    pdf_bytes = HTML(string=html_str).write_pdf()
    filename = f"{listing.get('listing_no', listing_id)}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
