"""PDF report generation - ReportLab + Sarabun Thai font (v2.10)"""
from io import BytesIO
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from app.db import get_supabase

router = APIRouter()

# ============================================================
# 🆕 v2.10: Thai font registration — Sarabun (bundled with app)
# ============================================================
THAI_FONT = "Helvetica"
THAI_FONT_BOLD = "Helvetica-Bold"

# Look for bundled font first (app/fonts/), then fallback to system fonts
APP_DIR = Path(__file__).resolve().parent.parent  # app/
BUNDLED_FONT_DIR = APP_DIR / "fonts"

_font_candidates = [
    # Priority 1: Bundled Sarabun in repo
    (BUNDLED_FONT_DIR / "Sarabun-Regular.ttf", BUNDLED_FONT_DIR / "Sarabun-Bold.ttf"),
    # Priority 2: System fonts (if available)
    (Path("/usr/share/fonts/truetype/tlwg/Sarabun.ttf"), Path("/usr/share/fonts/truetype/tlwg/Sarabun-Bold.ttf")),
    (Path("/usr/share/fonts/truetype/tlwg/Norasi.ttf"), Path("/usr/share/fonts/truetype/tlwg/Norasi-Bold.ttf")),
    (Path("/usr/share/fonts/truetype/tlwg/Garuda.ttf"), Path("/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf")),
]

for regular_path, bold_path in _font_candidates:
    if regular_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("ThaiFont", str(regular_path)))
            THAI_FONT = "ThaiFont"
            if bold_path.exists():
                pdfmetrics.registerFont(TTFont("ThaiFont-Bold", str(bold_path)))
                THAI_FONT_BOLD = "ThaiFont-Bold"
            else:
                THAI_FONT_BOLD = "ThaiFont"  # use regular as bold fallback
            print(f"[PDF] ✓ Thai font registered: {regular_path}")
            break
        except Exception as e:
            print(f"[PDF] ⚠ Failed to load {regular_path}: {e}")
            continue
else:
    print("[PDF] ⚠ No Thai font found — Thai characters may not render correctly")

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


def build_pdf(listing: dict, calc: dict, broker_name: str = "") -> bytes:
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
    seller_name = listing.get("seller_name") or "-"

    story = []

    # ============================================================
    # Header
    # ============================================================
    story.append(Paragraph(title, style_title))
    story.append(Paragraph("บ้านพร้อม BY NaYoo — มีครบ จบจริง", style_subtitle))

    # ============================================================
    # 🆕 v2.10: Parties (ลูกค้า / นายหน้า / Listing No / วันที่)
    # ============================================================
    parties_data = [
        ["ลูกค้า (ผู้ขาย)", seller_name, "Listing No", listing_no],
        ["นายหน้า", broker_name or "-", "วันที่", today],
    ]
    parties_table = Table(parties_data, colWidths=[3 * cm, 6.5 * cm, 2.5 * cm, 5 * cm])
    parties_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), THAI_FONT, 9),
        ('FONT', (0, 0), (0, -1), THAI_FONT_BOLD, 9),
        ('FONT', (2, 0), (2, -1), THAI_FONT_BOLD, 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#475569")),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor("#475569")),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('LINEBELOW', (0, 0), (-1, 0), 0.3, colors.HexColor("#e5e7eb")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 0.3 * cm))

    # ============================================================
    # Property info
    # ============================================================
    story.append(Paragraph("ข้อมูลทรัพย์", style_h3))

    property_type_th = {
        "LAND_ONLY": "ที่ดิน",
        "CONDO": "ห้องชุด",
        "HOUSE": "สิ่งปลูกสร้าง+ที่ดิน",
    }.get(listing.get("property_type", ""), listing.get("property_type", "-"))

    seller_type_th = {
        "individual": "บุคคลธรรมดา",
        "corporate": "นิติบุคคล",
    }.get(listing.get("seller_type", ""), "-")

    acquisition_type_th = {
        "bought": "ซื้อมาเอง",
        "inherited": "มรดก",
        "gift": "ให้โดยเสน่หา",
    }.get(listing.get("acquisition_type", ""), "-")

    # 🆕 v2.10: Show area info
    area_rows = []
    if listing.get("land_total_sq_wah"):
        area_rows.append([
            "พื้นที่ดิน",
            f"{listing.get('land_rai', 0)} ไร่ {listing.get('land_ngan', 0)} งาน {listing.get('land_sq_wah', 0)} ตร.ว. (รวม {listing.get('land_total_sq_wah')} ตร.ว.)"
        ])
    elif listing.get("land_rai") or listing.get("land_ngan") or listing.get("land_sq_wah"):
        area_rows.append([
            "พื้นที่ดิน",
            f"{listing.get('land_rai', 0)} ไร่ {listing.get('land_ngan', 0)} งาน {listing.get('land_sq_wah', 0)} ตร.ว."
        ])
    if listing.get("condo_floor_area_sqm"):
        area_rows.append(["พื้นที่ห้องชุด", f"{listing.get('condo_floor_area_sqm')} ตร.ม."])
        if listing.get("condo_building_name"):
            area_rows.append(["อาคาร / ชั้น", f"{listing.get('condo_building_name')} / {listing.get('condo_floor', '-')}"])
    if listing.get("building_floor_area_sqm"):
        area_rows.append(["พื้นที่อาคาร", f"{listing.get('building_floor_area_sqm')} ตร.ม."])

    prop_data = [
        ["ประเภททรัพย์", property_type_th],
        ["ผู้ขาย", f"{seller_type_th} ({acquisition_type_th})"],
    ] + area_rows + [
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

    # ============================================================
    # WF2 Redemption section
    # ============================================================
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

    # ============================================================
    # Line items
    # ============================================================
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

    # ============================================================
    # Footer
    # ============================================================
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
async def generate_pdf(listing_id: str):
    """Generate PDF + download"""
    sb = get_supabase()
    res = sb.table("listings").select("*").eq("id", listing_id).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบ listing")
    listing = res.data[0]

    # 🆕 v2.10: Fetch broker name from users table
    broker_name = ""
    user_id = listing.get("user_id")
    if user_id:
        try:
            user_res = sb.table("users").select("name").eq("id", user_id).limit(1).execute()
            if user_res.data:
                broker_name = user_res.data[0].get("name", "")
        except Exception as e:
            print(f"[PDF] Failed to fetch broker name: {e}")

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
        pdf_bytes = build_pdf(listing, calc, broker_name=broker_name)
    except Exception as e:
        raise HTTPException(500, f"PDF generation error: {e}")

    filename = f"{listing.get('listing_no', listing_id)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
