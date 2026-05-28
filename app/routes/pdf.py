"""PDF report generation - ReportLab (pure Python, no apt deps)"""
from io import BytesIO
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from app.auth import get_current_agent
from app.db import get_supabase

router = APIRouter()

# Register Thai font (fallback to Helvetica if not found)
THAI_FONT = "Helvetica"
THAI_FONT_BOLD = "Helvetica-Bold"

try:
    # Try to use built-in fonts that support Thai
    import os
    for font_path in [
        "/usr/share/fonts/truetype/tlwg/Garuda.ttf",
        "/usr/share/fonts/truetype/tlwg/Norasi.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("Thai", font_path))
            THAI_FONT = "Thai"
            THAI_FONT_BOLD = "Thai"
            break
except Exception:
    pass

# Brand colors
BRAND_BLUE = colors.HexColor("#2AABE0")
BRAND_ORANGE = colors.HexColor("#F05A28")


def format_thai_baht(amount) -> str:
    if amount is None:
        return "-"
    try:
        return f"{float(amount):,.2f}"
    except (ValueError, TypeError):
        return "-"


def build_pdf(listing: dict, calc: dict) -> bytes:
    """Build PDF using ReportLab"""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        'Title', parent=styles['Title'], fontName=THAI_FONT_BOLD,
        fontSize=20, textColor=BRAND_BLUE, alignment=TA_CENTER, spaceAfter=6,
    )
    style_subtitle = ParagraphStyle(
        'SubTitle', parent=styles['Normal'], fontName=THAI_FONT,
        fontSize=10, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=20,
    )
    style_h3 = ParagraphStyle(
        'H3', parent=styles['Heading3'], fontName=THAI_FONT_BOLD,
        fontSize=12, textColor=BRAND_BLUE,
        backColor=colors.HexColor("#f3f4f6"), borderPadding=6, spaceAfter=10, spaceBefore=12,
    )
    style_normal = ParagraphStyle(
        'Normal', parent=styles['Normal'], fontName=THAI_FONT, fontSize=10,
    )

    workflow = calc.get("calculation_type", "transfer")
    title = "ค่าใช้จ่ายขายฝาก" if workflow == "leaseback" else "ค่าใช้จ่ายวันโอน"
    listing_no = listing.get("listing_no", "N/A")
    today = datetime.now().strftime("%d/%m/%Y")

    story = []

    # Header
    story.append(Paragraph(title, style_title))
    story.append(Paragraph("บ้านพร้อม BY NaYoo — มีครบ จบจริง", style_subtitle))

    # Meta info
    meta_data = [
        [f"Listing No: {listing_no}", f"วันที่: {today}"],
    ]
    meta_table = Table(meta_data, colWidths=[9 * cm, 9 * cm])
    meta_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), THAI_FONT, 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.grey),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(meta_table)

    # Property info
    story.append(Paragraph("ข้อมูลทรัพย์", style_h3))

    prop_data = [
        ["ประเภททรัพย์", listing.get('property_type', '-')],
        ["ผู้ขาย", f"{listing.get('seller_type', '-')} ({listing.get('acquisition_type', '-')})"],
        ["ราคาขาย", format_thai_baht(listing.get('sale_price'))],
        ["ราคาประเมิน", format_thai_baht(listing.get('appraisal_price_total'))],
        ["Tax Base (MAX)", format_thai_baht(calc.get('tax_base'))],
    ]
    prop_table = Table(prop_data, colWidths=[5 * cm, 13 * cm])
    prop_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), THAI_FONT, 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor("#e5e7eb")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
        ('FONT', (0, -1), (-1, -1), THAI_FONT_BOLD, 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(prop_table)

    # WF2 Redemption section
    if workflow == "leaseback":
        story.append(Paragraph("ยอดกำหนดสินไถ่", style_h3))
        redemption_data = [
            ["ราคาคาดว่าขายออก", format_thai_baht(listing.get('expected_market_price'))],
            ["ราคาขายฝากที่ตกลง", format_thai_baht(listing.get('sale_price'))],
            ["หัก ดอกเบี้ยล่วงหน้า", f"- {format_thai_baht(calc.get('advance_interest_amount'))}"],
            ["หัก ค่าปากถุง 5%", f"- {format_thai_baht(calc.get('mouth_money_fee'))}"],
            ["เหลือเงิน", format_thai_baht(calc.get('remaining_cash'))],
            ["ยอดกำหนดสินไถ่", format_thai_baht(calc.get('redemption_amount'))],
        ]
        r_table = Table(redemption_data, colWidths=[7 * cm, 11 * cm])
        r_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), THAI_FONT, 10),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEBELOW', (0, 0), (-1, -3), 0.5, colors.HexColor("#e5e7eb")),
            ('BACKGROUND', (0, -2), (-1, -1), colors.HexColor("#fef3c7")),
            ('FONT', (0, -2), (-1, -1), THAI_FONT_BOLD, 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(r_table)

    # Line items
    story.append(Paragraph("รายละเอียดค่าใช้จ่าย", style_h3))

    line_items = calc.get("line_items", [])
    item_rows = [["รายการ", "สูตร", "จำนวน (บาท)"]]
    for it in line_items:
        item_rows.append([
            it.get('description', ''),
            it.get('formula', ''),
            format_thai_baht(it.get('amount')),
        ])
    item_rows.append(["รวมค่าใช้จ่ายทั้งหมด", "", format_thai_baht(calc.get('total_cost'))])

    item_table = Table(item_rows, colWidths=[7.5 * cm, 6.5 * cm, 4 * cm])
    item_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONT', (0, 0), (-1, 0), THAI_FONT_BOLD, 10),
        ('ALIGN', (0, 0), (-2, 0), 'LEFT'),
        ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
        # Body
        ('FONT', (0, 1), (-1, -2), THAI_FONT, 9),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor("#e5e7eb")),
        # Total row
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
        ('FONT', (0, -1), (-1, -1), THAI_FONT_BOLD, 11),
        ('SPAN', (0, -1), (1, -1)),
        # Padding
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(item_table)

    # Footer
    story.append(Spacer(1, 1 * cm))
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontName=THAI_FONT,
        fontSize=8, textColor=colors.grey, alignment=TA_CENTER,
    )
    story.append(Paragraph(
        "เอกสารนี้สร้างโดยระบบ NaYoo Real Estate — เพื่อประมาณการค่าใช้จ่ายเบื้องต้น<br/>"
        "ตัวเลขสุดท้ายต้องยืนยันที่สำนักงานที่ดิน",
        footer_style,
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


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
        pdf_bytes = build_pdf(listing, calc)
    except Exception as e:
        raise HTTPException(500, f"PDF generation error: {e}")

    filename = f"{listing.get('listing_no', listing_id)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
