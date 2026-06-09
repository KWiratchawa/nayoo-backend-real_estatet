"""PDF report generation - ReportLab + Sarabun + HarfBuzz Thai shaping (v2.12)"""
from io import BytesIO
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable
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

_REG_FONT_PATH = None   # actual file used for ThaiFont (for HarfBuzz)
_BOLD_FONT_PATH = None   # actual file used for ThaiFont-Bold

for regular_path, bold_path in _font_candidates:
    if regular_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("ThaiFont", str(regular_path)))
            THAI_FONT = "ThaiFont"
            _REG_FONT_PATH = regular_path
            if bold_path.exists():
                pdfmetrics.registerFont(TTFont("ThaiFont-Bold", str(bold_path)))
                THAI_FONT_BOLD = "ThaiFont-Bold"
                _BOLD_FONT_PATH = bold_path
            else:
                THAI_FONT_BOLD = "ThaiFont"
                _BOLD_FONT_PATH = regular_path
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

# Thailand timezone (UTC+7, no DST) — server (Render) runs in UTC,
# so datetime.now() would show the wrong day near midnight Thai time.
TH_TZ = timezone(timedelta(hours=7))

# ============================================================
# 🆕 v2.12: HarfBuzz Thai shaping
# ------------------------------------------------------------
# ReportLab does NOT apply OpenType GPOS, so Sarabun tone marks
# collide with upper vowels (e.g. ซื้อ, เบื้อง, ที่). We shape the
# text with HarfBuzz to get the correct per-glyph (x_offset,
# y_offset, x_advance), then draw each glyph individually.
# If uharfbuzz is unavailable we fall back to plain Paragraph
# (the previous behaviour) — no regression.
# ============================================================
try:
    import uharfbuzz as hb
    HB_AVAILABLE = True
except Exception as _hb_err:  # pragma: no cover
    HB_AVAILABLE = False
    print(f"[PDF] uharfbuzz not available ({_hb_err}); Thai shaping disabled — using ReportLab fallback")

# rl_font_name -> (hb_font, upem, gid2char)
HB_FONTS: dict = {}


def _build_hb_font(path):
    """Load a font into HarfBuzz and build a glyph-id → character map.

    Shaped glyph_infos give glyph IDs; to draw them with ReportLab's
    drawString we map each GID back to a Unicode char via the font's
    cmap. This covers every glyph our text can reach (incl. the
    nikhahit/sara-aa that SARA AM ำ decomposes into during shaping).
    """
    blob = hb.Blob.from_file_path(str(path))
    face = hb.Face(blob)
    upem = face.upem
    font = hb.Font(face)
    gid2char = {}
    codepoints = (
        list(range(0x20, 0x7F))      # ASCII
        + list(range(0xA0, 0x100))   # Latin-1 (incl. × U+00D7)
        + list(range(0x0E00, 0x0E80))  # Thai
        + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026]  # punctuation
    )
    for cp in codepoints:
        try:
            gid = font.get_nominal_glyph(cp)
        except Exception:
            gid = None
        if gid:  # 0 / None = not in font
            gid2char.setdefault(gid, chr(cp))
    return font, upem, gid2char


if HB_AVAILABLE and THAI_FONT == "ThaiFont" and _REG_FONT_PATH is not None:
    try:
        HB_FONTS["ThaiFont"] = _build_hb_font(_REG_FONT_PATH)
        HB_FONTS["ThaiFont-Bold"] = _build_hb_font(_BOLD_FONT_PATH or _REG_FONT_PATH)
        print("[PDF] ✓ HarfBuzz Thai shaping enabled")
    except Exception as _e:
        print(f"[PDF] ⚠ HarfBuzz init failed ({_e}); using ReportLab fallback")
        HB_FONTS = {}

# Shaping is usable only if HB loaded AND we have a real Thai font registered
_USE_SHAPING = HB_AVAILABLE and bool(HB_FONTS)

# Disable the 'ccmp' feature: Sarabun's ccmp substitutes stacked tone marks
# with pre-positioned variant glyphs that have NO cmap entry (so we couldn't
# map them back to a character to draw). With ccmp off, marks stay as their
# nominal glyphs and HarfBuzz lifts them via GPOS y_offset instead — which we
# can both resolve and draw correctly.
_HB_FEATURES = {"ccmp": False}


class ShapedText(Flowable):
    """A flowable that renders one cell of (Thai) text using HarfBuzz
    shaping, so tone marks and vowels are positioned correctly.

    Reads font / size / leading / colour / alignment from a ReportLab
    ParagraphStyle so it can be a drop-in for Paragraph inside Tables.
    Supports word-wrap on spaces, explicit <br/> breaks, and strips the
    redundant <b> tags used by the bold styles.
    """

    def __init__(self, text, style):
        super().__init__()
        self.style = style
        self.font_name = style.fontName
        self.font_size = style.fontSize
        self.leading = style.leading or (style.fontSize * 1.2)
        self.color = getattr(style, "textColor", None) or colors.black
        self.align = getattr(style, "alignment", TA_LEFT)
        self._hb_font, self._upem, self._gid2char = HB_FONTS[self.font_name]
        self.text = self._clean(text)
        self.lines = [self.text]
        self.avail_width = 0.0

    @staticmethod
    def _clean(raw):
        t = str(raw)
        for br in ("<br/>", "<br />", "<br>"):
            t = t.replace(br, "\n")
        return t.replace("<b>", "").replace("</b>", "")

    def _shape(self, s):
        """Return list of (gid, x_offset, y_offset, x_advance) in font units."""
        if not s:
            return []
        buf = hb.Buffer()
        buf.add_str(s)
        buf.guess_segment_properties()
        hb.shape(self._hb_font, buf, _HB_FEATURES)
        out = []
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((info.codepoint, pos.x_offset, pos.y_offset, pos.x_advance))
        return out

    def _text_width(self, s):
        scale = self.font_size / self._upem
        return sum(adv for _, _, _, adv in self._shape(s)) * scale

    def _wrap_lines(self, text, avail_width):
        lines = []
        for para in text.split("\n"):
            words = para.split(" ")
            cur = ""
            for w in words:
                trial = w if cur == "" else cur + " " + w
                if cur == "" or self._text_width(trial) <= avail_width:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
        return lines or [""]

    def wrap(self, avail_width, avail_height):
        self.avail_width = avail_width
        self.lines = self._wrap_lines(self.text, avail_width)
        self.width = avail_width
        self.height = self.leading * max(1, len(self.lines))
        return self.width, self.height

    def draw(self):
        c = self.canv
        scale = self.font_size / self._upem
        c.setFont(self.font_name, self.font_size)
        c.setFillColor(self.color)
        for i, line in enumerate(self.lines):
            glyphs = self._shape(line)
            line_w = sum(adv for _, _, _, adv in glyphs) * scale
            if self.align == TA_RIGHT:
                start_x = self.avail_width - line_w
            elif self.align == TA_CENTER:
                start_x = (self.avail_width - line_w) / 2.0
            else:
                start_x = 0.0
            baseline = self.height - self.font_size - i * self.leading
            pen_x = start_x
            for gid, x_off, y_off, x_adv in glyphs:
                ch = self._gid2char.get(gid)
                if ch is not None and ch != " ":
                    c.drawString(pen_x + x_off * scale, baseline + y_off * scale, ch)
                pen_x += x_adv * scale


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

    # 🆕 v2.12: render Thai text via HarfBuzz shaping (correct mark
    # positioning); fall back to Paragraph when shaping is unavailable.
    def P(text, style=style_cell):
        if text is None or text == "":
            text = "-"
        if _USE_SHAPING and style.fontName in HB_FONTS:
            return ShapedText(str(text), style)
        return Paragraph(str(text), style)

    # ============================================================
    # Extract data
    # ============================================================
    workflow = calc.get("calculation_type", "transfer")
    title = "ค่าใช้จ่ายขายฝาก" if workflow == "leaseback" else "ค่าใช้จ่ายวันโอน"
    listing_no = listing.get("listing_no", "N/A")
    today = datetime.now(TH_TZ).strftime("%d/%m/%Y")
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
    story.append(P(
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
