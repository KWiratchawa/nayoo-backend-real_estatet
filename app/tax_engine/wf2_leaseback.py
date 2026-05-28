"""
tax_engine.wf2_leaseback
~~~~~~~~~~~~~~~~~~~~~~~~
Workflow 2: คำนวณค่าใช้จ่ายและความเป็นไปได้ของการรับซื้อฝาก

สูตรหลัก (จาก แนวคิดคำนวณค่าใช้จ่ายขายฝาก.pdf):
  1. ดอกเบี้ยล่วงหน้า = ราคาขายฝาก × 1.25%/เดือน × 3 เดือน
  2. ค่าปากถุง = ราคาขายฝาก × 5%
  3. ยอดสินไถ่ = ราคาขายฝาก + ดอกเบี้ย × ระยะเวลาเต็ม
  4. ค่าใช้จ่ายวันโอน (เรียก WF1)
  5. เงินสุทธิที่ผู้ขายฝากได้ = ราคาขายฝาก - ดอกเบี้ย - ปากถุง - ค่าโอน
"""
from decimal import Decimal

from .config import (
    LEASEBACK_LTV_THRESHOLD,
    ENGINE_VERSION,
)
from .models import (
    CostResponsibility,
    FeasibilityVerdict,
    LeasebackCalcInput,
    LeasebackCalcResult,
    TransferCalcInput,
)
from .utils import round_money
from .wf1_transfer import calculate_transfer_costs


# ============================================================================
# 1. ดอกเบี้ยล่วงหน้า
# ============================================================================

def calculate_advance_interest(
    repo_price: Decimal,
    rate_monthly: Decimal,
    months: int,
) -> Decimal:
    """
    ดอกเบี้ยล่วงหน้า = ราคาขายฝาก × อัตราต่อเดือน × จำนวนเดือน

    Source: แนวคิดคำนวณค่าใช้จ่ายขายฝาก.pdf
    Default: 2,500,000 × 1.25% × 3 = 93,750
    """
    return round_money(repo_price * rate_monthly * Decimal(months))


# ============================================================================
# 2. ค่าปากถุง
# ============================================================================

def calculate_mouth_money(repo_price: Decimal, rate: Decimal = Decimal("0.05")) -> Decimal:
    """
    ค่าปากถุง = ราคาขายฝาก × 5%

    Source: แนวคิดคำนวณค่าใช้จ่ายขายฝาก.pdf
    Default: 2,500,000 × 5% = 125,000
    """
    return round_money(repo_price * rate)


# ============================================================================
# 3. ยอดกำหนดสินไถ่
# ============================================================================

def calculate_redemption_amount(
    repo_price: Decimal,
    rate_monthly: Decimal,
    term_months: int,
) -> Decimal:
    """
    ยอดกำหนดสินไถ่ = ราคาขายฝาก × (1 + อัตราต่อเดือน × ระยะเวลาเต็ม)

    Source: แนวคิดคำนวณค่าใช้จ่ายขายฝาก.pdf
    Default: 2,500,000 × (1 + 1.25% × 9) = 2,500,000 × 1.1125 = 2,781,250
    """
    multiplier = Decimal("1") + (rate_monthly * Decimal(term_months))
    return round_money(repo_price * multiplier)


# ============================================================================
# 4. แบ่งภาระค่าใช้จ่ายวันโอน
# ============================================================================

def split_transfer_cost(
    total_transfer_cost: Decimal,
    paid_by: CostResponsibility,
) -> tuple[Decimal, Decimal]:
    """
    แบ่งค่าใช้จ่ายวันโอนตามดีลที่ตกลง

    Returns:
        (buyer_share, seller_share)
    """
    if paid_by == CostResponsibility.BUYER:
        return total_transfer_cost, Decimal("0")
    if paid_by == CostResponsibility.SELLER:
        return Decimal("0"), total_transfer_cost
    if paid_by == CostResponsibility.SPLIT:
        half = round_money(total_transfer_cost / Decimal("2"))
        return half, total_transfer_cost - half
    # NEGOTIABLE → default 50/50 (รอเจรจา)
    half = round_money(total_transfer_cost / Decimal("2"))
    return half, total_transfer_cost - half


# ============================================================================
# 5. ประเมินความเป็นไปได้
# ============================================================================

def assess_feasibility(
    net_proceeds: Decimal,
    outstanding_debts: Decimal,
    ltv_warning: bool,
) -> tuple[FeasibilityVerdict, str]:
    """
    เกณฑ์เบื้องต้น (auto):
    - ถ้าเงินสุทธิ < ภาระหนี้ → NO_GO (เงินไม่พอชำระหนี้)
    - มิฉะนั้น → PENDING (ส่งให้ทีมตรวจสอบความเสี่ยงอื่นๆ ก่อน)

    หมายเหตุ: ระบบไม่ตัดสินใจ GO เองโดยอัตโนมัติ — ต้องรอทีมตรวจสอบ
    เพราะมี factor อื่นที่ระบบประเมินไม่ได้ เช่น:
    - ความสามารถในการขายออกในตลาด
    - ทำเล/สภาพคล่อง
    - ประวัติผู้ขายฝาก
    - ความเสี่ยงการไม่ไถ่ถอน
    """
    if net_proceeds < outstanding_debts:
        shortage = outstanding_debts - net_proceeds
        return (
            FeasibilityVerdict.NO_GO,
            f"เงินสุทธิที่ผู้ขายฝากได้ ({net_proceeds:,.2f} บาท) "
            f"ไม่พอชำระหนี้ ({outstanding_debts:,.2f} บาท) "
            f"ขาดอยู่ {shortage:,.2f} บาท"
        )

    reason = "เงินสุทธิเพียงพอชำระหนี้ — รอทีมตรวจสอบความเสี่ยงอื่นๆ"
    if ltv_warning:
        reason += " (⚠ LTV เกิน 60% — ความเสี่ยงสูง)"
    return FeasibilityVerdict.PENDING, reason


# ============================================================================
# Main orchestrator
# ============================================================================

def calculate_leaseback_costs(inp: LeasebackCalcInput) -> LeasebackCalcResult:
    """
    คำนวณค่าใช้จ่ายขายฝากทั้งหมด (Workflow 2)
    """
    warnings: list[str] = []

    # --- LTV check ---
    ltv_ratio = inp.repo_price / inp.expected_market_price
    ltv_warning = ltv_ratio > LEASEBACK_LTV_THRESHOLD
    if ltv_warning:
        warnings.append(
            f"⚠ LTV = {float(ltv_ratio)*100:.2f}% เกินเกณฑ์ benchmark 60% — ความเสี่ยงสูง"
        )

    # --- 1. ดอกเบี้ยล่วงหน้า ---
    advance_interest = calculate_advance_interest(
        inp.repo_price,
        inp.interest_rate_monthly,
        inp.advance_interest_months,
    )

    # --- 2. ค่าปากถุง ---
    mouth_money = calculate_mouth_money(inp.repo_price)

    # --- 3. ยอดสินไถ่ ---
    redemption = calculate_redemption_amount(
        inp.repo_price,
        inp.interest_rate_monthly,
        inp.total_term_months,
    )

    # --- 4. ค่าใช้จ่ายวันโอน (เรียก WF1) ---
    # หมายเหตุ: ใช้ ราคาขายฝาก เป็น sale_price ใน WF1
    transfer_input = TransferCalcInput(
        seller_type=inp.seller_type,
        acquisition_type=inp.acquisition_type,
        acquisition_year=inp.acquisition_year,
        sale_year=inp.sale_year,
        years_in_household_registration=inp.years_in_household_registration,
        is_in_bangkok_metro=inp.is_in_bangkok_metro,
        sale_price=inp.repo_price,
        appraisal_price=inp.appraisal_price,
        has_mortgage=False,           # ขายฝากไม่มีจำนองพร้อมโอน
        mortgage_amount=Decimal("0"),
        has_intent_to_trade=inp.has_intent_to_trade,
    )
    transfer_result = calculate_transfer_costs(transfer_input)

    # --- 5. แบ่งภาระค่าโอน ---
    buyer_share, seller_share = split_transfer_cost(
        transfer_result.total_cost,
        inp.transfer_cost_paid_by,
    )

    # ใส่ cost_responsibility ในแต่ละ line item
    for li in transfer_result.line_items:
        li.cost_responsibility = inp.transfer_cost_paid_by

    # --- 6. เงินสุทธิที่ผู้ขายฝากได้ ---
    # เงินที่ได้ก่อนหักค่าโอน
    cash_before_transfer = inp.repo_price - advance_interest - mouth_money
    # หักเฉพาะส่วนที่ผู้ขายต้องรับผิดชอบ
    net_proceeds = cash_before_transfer - seller_share

    # --- 7. ประเมินความเป็นไปได้ ---
    covers_debts = net_proceeds >= inp.outstanding_debts
    verdict, verdict_reason = assess_feasibility(
        net_proceeds, inp.outstanding_debts, ltv_warning
    )

    return LeasebackCalcResult(
        repo_price=inp.repo_price,
        expected_market_price=inp.expected_market_price,
        ltv_ratio=round_money(ltv_ratio, places=4) if False else ltv_ratio.quantize(Decimal("0.0001")),
        ltv_warning=ltv_warning,
        advance_interest_amount=advance_interest,
        mouth_money_fee=mouth_money,
        redemption_amount=redemption,
        transfer_costs=transfer_result,
        cash_received_before_transfer=round_money(cash_before_transfer),
        net_proceeds_to_seller=round_money(net_proceeds),
        outstanding_debts=inp.outstanding_debts,
        covers_debts=covers_debts,
        feasibility_verdict=verdict,
        feasibility_reason=verdict_reason,
        warnings=warnings,
        engine_version=ENGINE_VERSION,
    )
