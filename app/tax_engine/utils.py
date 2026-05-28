"""
tax_engine.utils
~~~~~~~~~~~~~~~~
ฟังก์ชันยูทิลิตี้ที่ใช้ร่วมกันในทุก workflow
"""
from decimal import Decimal, ROUND_HALF_UP

from .config import (
    SQWAH_PER_RAI,
    SQWAH_PER_NGAN,
)


# ============================================================================
# พื้นที่ดิน
# ============================================================================

def convert_land_area(rai: int, ngan: int, sq_wah: Decimal | float | int) -> Decimal:
    """
    แปลงพื้นที่ ไร่-งาน-ตารางวา → ตารางวารวม

    มาตรฐานไทย:
    - 1 ไร่ = 4 งาน = 400 ตารางวา
    - 1 งาน = 100 ตารางวา

    Args:
        rai: จำนวนไร่
        ngan: จำนวนงาน (0-3)
        sq_wah: จำนวนตารางวา (0-99.99)

    Returns:
        ตารางวารวมเป็น Decimal

    Examples:
        >>> convert_land_area(1, 0, 0)
        Decimal('400')
        >>> convert_land_area(0, 1, 50)
        Decimal('150')
        >>> convert_land_area(2, 3, 25.5)
        Decimal('1125.5')
    """
    if rai < 0 or ngan < 0 or Decimal(str(sq_wah)) < 0:
        raise ValueError("พื้นที่ต้องไม่เป็นค่าลบ")
    if ngan >= 4:
        raise ValueError("จำนวนงานต้องน้อยกว่า 4 (เพราะ 4 งาน = 1 ไร่)")

    sq_wah_dec = Decimal(str(sq_wah))
    if sq_wah_dec >= 100:
        raise ValueError("จำนวนตารางวาต้องน้อยกว่า 100 (เพราะ 100 วา = 1 งาน)")

    total = (
        Decimal(rai) * SQWAH_PER_RAI
        + Decimal(ngan) * SQWAH_PER_NGAN
        + sq_wah_dec
    )
    return total


# ============================================================================
# ปีถือครอง
# ============================================================================

def calculate_holding_years(acquisition_year: int, sale_year: int) -> int:
    """
    คำนวณจำนวนปีถือครองตาม ป.100/2543 ข้อ 6 วรรค 3

    กฎ:
    - นับตั้งแต่ปีที่ได้กรรมสิทธิ์ ถึงปีที่โอน
    - เศษของปี ให้นับเป็นหนึ่งปี
    - ถ้าเกิน 10 ปี ให้นับเพียง 10 ปี

    Args:
        acquisition_year: ปี พ.ศ. ที่ได้มา
        sale_year: ปี พ.ศ. ที่จะโอน

    Returns:
        จำนวนปีถือครอง (1-10)

    Examples:
        >>> calculate_holding_years(2562, 2567)
        5
        >>> calculate_holding_years(2567, 2567)
        1
        >>> calculate_holding_years(2550, 2567)
        10
    """
    if sale_year < acquisition_year:
        raise ValueError(f"ปีโอน ({sale_year}) ต้องมากกว่าหรือเท่ากับปีได้มา ({acquisition_year})")

    diff = sale_year - acquisition_year
    # เศษของปี = +1 (กรณีปีเดียวกัน นับ 1 ปี)
    years = max(1, diff if diff > 0 else 1)
    if diff == 0:
        years = 1
    else:
        # หาก diff > 0 → นับเป็น diff ปี (ปีนั้นเศษ → +1 อยู่แล้วในตัว)
        years = diff
        # เนื่องจาก ป.100 บอกว่า "เศษของปีให้นับเป็นหนึ่งปี"
        # ดังนั้นถ้า diff=1 (ได้มา 2566 ขาย 2567) = ถือ 1 ปี ก็คือ diff = 1
        # ถ้า diff=5 (ได้มา 2562 ขาย 2567) = 5 ปี
    # cap ที่ 10 ปี
    return min(years, 10)


# ============================================================================
# Progressive tax calculator
# ============================================================================

def calculate_progressive_tax(
    income: Decimal,
    brackets: list[tuple[Decimal, Decimal]],
) -> Decimal:
    """
    คำนวณภาษีตามอัตราขั้นบันได (progressive)

    Args:
        income: เงินได้สุทธิ (บาท)
        brackets: ตารางขั้น [(upper_bound_1, rate_1), (upper_bound_2, rate_2), ...]
                  เรียงจากน้อยไปมาก ตัวสุดท้ายต้องครอบคลุมทุกค่า

    Returns:
        ภาษีที่คำนวณได้

    Example (อัตราปัจจุบัน WHT brackets):
        income = 200,000
        bracket แรก = (300,000, 0.05)
        → ภาษี = 200,000 × 5% = 10,000

        income = 700,000
        → (300,000 × 5%) + (200,000 × 10%) + (200,000 × 15%) = 15K + 20K + 30K = 65,000
    """
    if income <= 0:
        return Decimal("0")

    tax = Decimal("0")
    lower_bound = Decimal("0")
    remaining = income

    for upper_bound, rate in brackets:
        bracket_size = upper_bound - lower_bound
        taxable_in_bracket = min(remaining, bracket_size)

        if taxable_in_bracket <= 0:
            break

        tax += taxable_in_bracket * rate
        remaining -= taxable_in_bracket
        lower_bound = upper_bound

        if remaining <= 0:
            break

    return tax


# ============================================================================
# Rounding utility
# ============================================================================

def round_money(value: Decimal, places: int = 2) -> Decimal:
    """
    ปัดเศษเงินเป็นทศนิยม N ตำแหน่ง (default 2 = สตางค์)
    ใช้ ROUND_HALF_UP ตามมาตรฐานสรรพากร
    """
    quantizer = Decimal("0.01") if places == 2 else Decimal(f"1e-{places}")
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def max_decimal(a: Decimal, b: Decimal) -> Decimal:
    """หาค่าที่มากกว่าระหว่าง 2 Decimal"""
    return a if a >= b else b
