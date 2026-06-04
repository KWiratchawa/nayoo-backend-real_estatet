"""PDF report generation - ReportLab + Sarabun + Thai shaping (v2.11)"""
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
# Thai font registration
# ============================================================
THAI_FONT = "Helvetica"
THAI_FONT_BOLD = "Helvetica-Bold"

APP_DIR = Path(__file__).resolve().parent.parent
BUNDLED_FONT_DIR = APP_DIR / "fonts"

_font_candidates = [
    (BUNDLED_FONT_DIR / "Sarabun-Regular.ttf", BUNDLED_FONT_DIR / "Sarabun-Bold.ttf"),
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
                THAI_FONT_BOLD = "ThaiFont"
            # 🆕 v2.11: Register font family for Bold inside Paragraph <b> tags
            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            registerFontFamily('ThaiFont', normal='ThaiFont', bold=THAI_FONT_BOLD)
            print(f"[PDF] ✓ Thai font registered: {regular_path}")
            break
        except Exception as e:
            print(f"[PDF] ⚠ Failed to load {regular_path}: {e}")
            continue
else:
    print("[PDF] ⚠ No Thai font found — Thai characters may not render correctly")

BRAND_BLUE = colors.HexColor("#2AABE0")
BRAND_ORANGE = colors.HexColor("#F05A28")


def fmt_baht(amount) -> str:
    if amount is None:
        return "-"
    try:
        return f"{float(amount):,.2f}"
    except (ValueError, TypeError):
        return "-"


def build_pdf(listing: dict, calc: dict, broker_name: str = "") -> bytes:
    """Build PDF — ใช้ Paragraph สำหรับ Thai text ทุกที่ (v2.11)"""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    # ============================================================
    # Styles
    # ============================================================
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

    # 🆕 v2.11: Paragraph styles for cell content (Thai shaping)
    style_cell = ParagraphStyle(
        'Cell', parent=styles['Normal'], fontName=THAI_FONT,
        fontSize=10, leading=14,
    )
    style_cell_bold = ParagraphStyle(
        'CellBold', parent=styles['Normal'], fontName=THAI_FONT_BOLD,
        fontSize=10, leading=14, textColor=colors.HexColor("#475569"),
    )
    style_cell_right = ParagraphStyle(
        'CellRight', parent=styles['Normal'], fontName=THAI_FONT,
        fontSize=10, leading=14, alignment=TA_RIGHT,
    )
    style_cell_right_bold = ParagraphStyle(
        'CellRightBold', parent=styles['Normal'], fontName=THAI_FONT_BOLD,
        fontSize=11, leading=14, alignment=TA_RIGHT,
    )
    style_cell_header = ParagraphStyle(
        'CellHeader', parent=styles['Normal'], fontName=THAI_FONT_BOLD,
        fontSize=10, leading=14, textColor=colors.white,
    )
    style_cell_header_right = ParagraphStyle(
        'CellHeaderRight', parent=styles['Normal'], fontName=THAI_FONT_BOLD,
        fontSize=10, leading=14, textColor=colors.white, alignment=TA_RIGHT,
    )
    style_cell_small = ParagraphStyle(
        'CellSmall', parent=styles['Normal'], fontName=THAI_FONT,
        fontSize=9, leading=12,
    )

    # 🆕 v2.11: helper to wrap Thai text in Paragraph
    def P(text, style=style_cell):
        """Wrap text in Paragraph for Thai shaping support"""
        if text is None or text == "":
            return Paragraph("-", style)
        return Paragraph(str(text), style)

    # ============================================================
    # Extract data
    # ============================================================
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
    # Parties (ลูกค้า / นายหน้า / Listing / Date)
    # ============================================================
    parties_data = [
        [P("ลูกค้า (ผู้ขาย)", style_cell_bold), P(seller_name), P("Listing No", style_cell_bold), P(listing_no)],
        [P("นายหน้า", style_cell_bold), P(broker_name or "-"), P("วันที่", style_cell_bold), P(today)],
    ]
    parties_table = Table(parties_data, colWidths=[3 * cm, 6.5 * cm, 2.5 * cm, 5 * cm])
    parties_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('LINEBELOW', (0, 0), (-1, 0), 0.3, colors.HexColor("#e5e7eb")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
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

    area_rows = []
    if listing.get("land_total_sq_wah") or listing.get("land_rai") or listing.get("land_ngan") or listing.get("land_sq_wah"):
        total_sqwah = listing.get("land_total_sq_wah")
        area_text = f"{listing.get('land_rai', 0)} ไร่ {listing.get('land_ngan', 0)} งาน {listing.get('land_sq_wah', 0)} ตร.ว."
        if total_sqwah:
            area_text += f" (รวม {total_sqwah} ตร.ว.)"
        area_rows.append([P("พื้นที่ดิน", style_cell), P(area_text, style_cell_right)])

    if listing.get("condo_floor_area_sqm"):
        area_rows.append([P("พื้นที่ห้องชุด", style_cell), P(f"{listing.get('condo_floor_area_sqm')} ตร.ม.", style_cell_right)])
        if listing.get("condo_building_name"):
            area_rows.append([P("อาคาร / ชั้น", style_cell), P(f"{listing.get('condo_building_name')} / {listing.get('condo_floor', '-')}", style_cell_right)])

    if listing.get("building_floor_area_sqm"):
        area_rows.append([P("พื้นที่อาคาร", style_cell), P(f"{listing.get('building_floor_area_sqm')} ตร.ม.", style_cell_right)])

    # 🆕 v2.11: เลขโฉนด/ระวาง (ถ้ามี)
    if listing.get("title_deed_no"):
        deed_text = f"เลขที่ {listing.get('title_deed_no')}"
        if listing.get("land_no"):
            deed_text += f" / เลขที่ดิน {listing.get('land_no')}"
        if listing.get("rawang_code"):
            deed_text += f" / ระวาง {listing.get('rawang_code')}"
        area_rows.append([P("โฉนดที่ดิน", style_cell), P(deed_text, style_cell_right)])

    prop_data = [
        [P("ประเภททรัพย์", style_cell), P(property_type_th, style_cell_right)],
        [P("ผู้ขาย", style_cell), P(f"{seller_type_th} ({acquisition_type_th})", style_cell_right)],
    ] + area_rows + [
        [P("ราคาขาย", style_cell), P(fmt_baht(listing.get('sale_price')), style_cell_right)],
        [P("ราคาประเมิน", style_cell), P(fmt_baht(listing.get('appraisal_price_total')), style_cell_right)],
        [P("<b>Tax Base (MAX)</b>", style_cell_bold), P(f"<b>{fmt_baht(calc.get('tax_base'))}</b>", style_cell_right_bold)],
    ]
    prop_table = Table(prop_data, colWidths=[5 * cm, 13 * cm])
    prop_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor("#e5e7eb")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
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
            [P("ราคาคาดว่าขายออก", style_cell), P(fmt_baht(listing.get('expected_market_price')), style_cell_right)],
            [P("ราคาขายฝากที่ตกลง", style_cell), P(fmt_baht(listing.get('sale_price')), style_cell_right)],
            [P("หัก ดอกเบี้ยล่วงหน้า", style_cell), P(f"- {fmt_baht(calc.get('advance_interest_amount'))}", style_cell_right)],
            [P("หัก ค่าปากถุง 5%", style_cell), P(f"- {fmt_baht(calc.get('mouth_money_fee'))}", style_cell_right)],
            [P("<b>เหลือเงิน</b>", style_cell_bold), P(f"<b>{fmt_baht(calc.get('remaining_cash'))}</b>", style_cell_right_bold)],
            [P("<b>ยอดกำหนดสินไถ่</b>", style_cell_bold), P(f"<b>{fmt_baht(calc.get('redemption_amount'))}</b>", style_cell_right_bold)],
        ]
        r_table = Table(redemption_data, colWidths=[7 * cm, 11 * cm])
        r_table.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -3), 0.5, colors.HexColor("#e5e7eb")),
            ('BACKGROUND', (0, -2), (-1, -1), colors.HexColor("#fef3c7")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(r_table)

    # ============================================================
    # Line items
    # ============================================================
    story.append(Paragraph("รายละเอียดค่าใช้จ่าย", style_h3))

    line_items = calc.get("line_items", [])
    item_rows = [[
        P("รายการ", style_cell_header),
        P("สูตร", style_cell_header),
        P("จำนวน (บาท)", style_cell_header_right),
    ]]
    for it in line_items:
        item_rows.append([
            P(it.get('description', ''), style_cell_small),
            P(it.get('formula', ''), style_cell_small),
            P(fmt_baht(it.get('amount')), style_cell_right),
        ])
    item_rows.append([
        P("<b>รวมค่าใช้จ่ายทั้งหมด</b>", style_cell_bold),
        P(""),
        P(f"<b>{fmt_baht(calc.get('total_cost'))}</b>", style_cell_right_bold),
    ])

    item_table = Table(item_rows, colWidths=[7.5 * cm, 6.5 * cm, 4 * cm])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor("#e5e7eb")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
        ('SPAN', (0, -1), (1, -1)),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(item_table)

    # ============================================================
    # 🆕 v2.11: Footer — ข้อความทางการ
    # ============================================================
    story.append(Spacer(1, 1 * cm))
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontName=THAI_FONT,
        fontSize=8, textColor=colors.grey, alignment=TA_CENTER, leading=12,
    )
    story.append(Paragraph(
        "เอกสารฉบับนี้จัดทำขึ้นเพื่อประมาณการค่าใช้จ่ายในการโอนกรรมสิทธิ์อสังหาริมทรัพย์เบื้องต้นเท่านั้น<br/>"
        "ค่าใช้จ่ายและภาษีที่แท้จริงให้ยึดตามการประเมินของสำนักงานที่ดิน ณ วันที่ทำนิติกรรม",
        footer_style,
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


@router.get("/{listing_id}/generate")
async def generate_pdf(listing_id: str):
    sb = get_supabase()
    res = sb.table("listings").select("*").eq("id", listing_id).execute()
    if not res.data:
        raise HTTPException(404, "ไม่พบ listing")
    listing = res.data[0]

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
