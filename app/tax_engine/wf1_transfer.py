"""
tax_engine.wf1_transfer
~~~~~~~~~~~~~~~~~~~~~~~
Workflow 1: คำนวณค่าใช้จ่ายวันโอน

ครอบคลุม:
  1. ค่าธรรมเนียมโอน (2% ของราคาประเมิน)
  2. ค่าคำขอ + พยาน (25 บาท)
  3. ภาษีเงินได้หัก ณ ที่จ่าย (บุคคลธรรมดา / นิติบุคคล)
  4. SBT 3.3% หรือ อากรแสตมป์ 0.5% (เลือกอย่างใดอย่างหนึ่ง)
  5. ค่าจดจำนอง 1% (ถ้ามี)
"""
from decimal import Decimal

from .config import (
    TRANSFER_FEE_RATE,
    REQUEST_WITNESS_TOTAL,
    MORTGAGE_FEE_RATE,
    SBT_EFFECTIVE_RATE,
    STAMP_DUTY_RATE,
    SBT_HOLDING_YEAR_THRESHOLD,
    HOUSEHOLD_REGISTRATION_THRESHOLD_YEARS,
    WHT_CORPORATE_RATE,
    WHT_CAP_RATE,
    WHT_NON_BKK_EXEMPTION,
    WHT_REAL_ESTATE_BRACKETS,
    DEDUCTION_RATES_BY_HOLDING_YEAR,
    INHERITED_DEDUCTION_RATE,
    TAX_CONFIG_VERSION,
    ENGINE_VERSION,
)
from .models import (
    AcquisitionType,
    CostLineItem,
    CostResponsibility,
    SellerType,
    TaxChoice,
    TransferCalcInput,
    TransferCalcResult,
    WhtCalculationDetail,
)
from .utils import (
    calculate_holding_years,
    calculate_progressive_tax,
    max_decimal,
    round_money,
)


# ============================================================================
# 1. ค่าธรรมเนียมโอน 2%
# ============================================================================

def calculate_transfer_fee(appraisal_price: Decimal, sale_price: Decimal) -> Decimal:
    """
    ค่าธรรมเนียมการโอน = 2% × MAX(ราคาขาย, ราคาประเมินกรมที่ดิน)

    Business Rule: ระบบใช้ MAX สำหรับทุก calculation เพื่อ conservative estimate
    Source: แนวคิดค่าใช้จ่ายวันโอน.pdf + business decision
    """
    base = max_decimal(sale_price, appraisal_price)
    return round_money(base * TRANSFER_FEE_RATE)


# ============================================================================
# 2. ค่าจดจำนอง 1%
# ============================================================================

def calculate_mortgage_fee(mortgage_amount: Decimal) -> Decimal:
    """
    ค่าจดจำนอง = 1% ของวงเงินจำนอง
    Source: แนวคิดค่าใช้จ่ายวันโอน.pdf
    """
    return round_money(mortgage_amount * MORTGAGE_FEE_RATE)


# ============================================================================
# 3. WHT บุคคลธรรมดา (มี 3 สูตรย่อยตามประเภทการได้มา)
# ============================================================================

def _get_deduction_rate_bought(holding_years: int) -> Decimal:
    """
    หาอัตราหักค่าใช้จ่ายตามปีถือครอง สำหรับกรณี "ซื้อมาเอง"
    ตามพ.ร.ฎ. 165 → 1ปี=92%, 2ปี=84%, ..., 8ปี+=50%

    Source: การคำนวณภาษีเงินได้บุคคลธรรมดาสำหรับอสังหาฯที่ไม่ใช่มรดก.pdf
    """
    if holding_years >= 8:
        return DEDUCTION_RATES_BY_HOLDING_YEAR[8]
    return DEDUCTION_RATES_BY_HOLDING_YEAR[holding_years]


def calculate_wht_individual(
    appraisal_price: Decimal,
    sale_price: Decimal,
    acquisition_type: AcquisitionType,
    holding_years: int,
    is_in_bangkok_metro: bool,
    has_intent_to_trade: bool,
) -> WhtCalculationDetail:
    """
    คำนวณ WHT บุคคลธรรมดาตาม ป.100/2543 ข้อ 6

    ขั้นตอน:
      1. เงินได้ = ราคาประเมิน (มาตรา 49 ทวิ)
         - ถ้ามรดก/ให้ + นอกเขต กทม. → หัก exemption 200K
      2. หักค่าใช้จ่าย:
         - มรดก / ให้โดยเสน่หา → 50% เสมอ
         - ซื้อมาเอง → ตามปีถือครอง (92%-50%)
      3. เงินได้สุทธิ ÷ ปีถือครอง = เงินได้เฉลี่ยต่อปี
      4. คำนวณภาษีตามอัตราก้าวหน้า (ไม่ยกเว้น 150K แรก) × ปีถือครอง
      5. ถ้า has_intent_to_trade=False → ใช้เพดาน 20% ของราคาขาย

    Args:
        appraisal_price: ราคาประเมินกรมธนารักษ์
        sale_price: ราคาขายที่ตกลง (ใช้คำนวณเพดาน)
        acquisition_type: ประเภทการได้มา
        holding_years: ปีถือครอง (1-10)
        is_in_bangkok_metro: อยู่ในเขต กทม./เทศบาล/พัทยา หรือไม่
        has_intent_to_trade: มุ่งค้าหากำไรหรือไม่

    Returns:
        WhtCalculationDetail พร้อมขั้นตอนการคำนวณครบ
    """
    # --- ขั้นที่ 1: เงินได้ = MAX(ราคาขาย, ราคาประเมิน) + exemption (ถ้ามี) ---
    # Business Rule: ใช้ MAX เป็น tax base สำหรับทุก calculation
    exemption = Decimal("0")
    if acquisition_type in (AcquisitionType.INHERITED, AcquisitionType.GIFT):
        # มรดก / ให้โดยเสน่หา นอกเขต → ยกเว้น 200K
        # Source: ป.100/2543 ข้อ 10(3)
        if not is_in_bangkok_metro:
            exemption = WHT_NON_BKK_EXEMPTION

    tax_base = max_decimal(sale_price, appraisal_price)
    income = max(Decimal("0"), tax_base - exemption)

    # --- ขั้นที่ 2: หักค่าใช้จ่าย ---
    if acquisition_type in (AcquisitionType.INHERITED, AcquisitionType.GIFT):
        deduction_rate = INHERITED_DEDUCTION_RATE
        deduction_basis = "มรดก/ให้โดยเสน่หา หักเหมา 50% (ป.100/2543 ข้อ 6(1))"
    else:  # BOUGHT
        deduction_rate = _get_deduction_rate_bought(holding_years)
        deduction_basis = (
            f"ซื้อมาเอง หักตามพ.ร.ฎ.165 ที่ {holding_years} ปี = {deduction_rate*100}%"
        )

    deduction_amount = income * deduction_rate
    net_income = income - deduction_amount

    # --- ขั้นที่ 3: เงินได้เฉลี่ยต่อปี ---
    income_per_year = net_income / Decimal(holding_years) if holding_years > 0 else net_income

    # --- ขั้นที่ 4: คำนวณภาษีตามขั้นบันได × ปีถือครอง ---
    # ไม่ยกเว้น 150K แรก → ใช้ WHT_REAL_ESTATE_BRACKETS (collapse 0-150K เข้า 5%)
    tax_per_year = calculate_progressive_tax(income_per_year, WHT_REAL_ESTATE_BRACKETS)
    total_tax_before_cap = tax_per_year * Decimal(holding_years)

    # --- ขั้นที่ 5: เพดาน 20% ของราคาขาย ---
    # Source: ป.100/2543 ข้อ 6 วรรค 4
    # เฉพาะกรณี "ไม่มุ่งค้าหากำไร"
    wht_cap = sale_price * WHT_CAP_RATE

    if has_intent_to_trade:
        # มุ่งค้าหากำไร → ไม่ใช้เพดาน
        final_tax = total_tax_before_cap
        cap_applied = False
    else:
        # ไม่มุ่งค้าหากำไร → ใช้เพดาน
        final_tax = min(total_tax_before_cap, wht_cap)
        cap_applied = total_tax_before_cap > wht_cap

    return WhtCalculationDetail(
        seller_type=SellerType.INDIVIDUAL,
        holding_years=holding_years,
        income=round_money(income),
        deduction_rate=deduction_rate,
        deduction_amount=round_money(deduction_amount),
        deduction_basis=deduction_basis,
        net_income=round_money(net_income),
        income_per_year=round_money(income_per_year),
        tax_per_year=round_money(tax_per_year),
        total_tax_before_cap=round_money(total_tax_before_cap),
        wht_cap=round_money(wht_cap),
        cap_applied=cap_applied,
        final_tax=round_money(final_tax),
        exemption_applied=exemption,
    )


# ============================================================================
# 4. WHT นิติบุคคล
# ============================================================================

def calculate_wht_corporate(
    sale_price: Decimal,
    appraisal_price: Decimal,
) -> WhtCalculationDetail:
    """
    WHT นิติบุคคล = 1% × MAX(ราคาขาย, ราคาประเมิน)
    Source: แนวคิดค่าใช้จ่ายวันโอน.pdf (ตารางนิติบุคคล)
    """
    base = max_decimal(sale_price, appraisal_price)
    tax = base * WHT_CORPORATE_RATE

    return WhtCalculationDetail(
        seller_type=SellerType.CORPORATE,
        holding_years=0,  # ไม่ใช้
        income=base,
        deduction_rate=Decimal("0"),
        deduction_amount=Decimal("0"),
        deduction_basis="นิติบุคคล ไม่มีการหักค่าใช้จ่าย",
        net_income=base,
        income_per_year=base,
        tax_per_year=tax,
        total_tax_before_cap=round_money(tax),
        wht_cap=Decimal("0"),
        cap_applied=False,
        final_tax=round_money(tax),
        exemption_applied=Decimal("0"),
    )


# ============================================================================
# 5. ตัดสินใจ SBT vs อากรแสตมป์
# ============================================================================

def decide_sbt_or_stamp(
    seller_type: SellerType,
    acquisition_type: AcquisitionType,
    holding_years: int,
    years_in_household_registration: int,
) -> tuple[TaxChoice, str]:
    """
    ตัดสินใจว่าจะเสีย SBT หรือ อากรแสตมป์
    Source: แนวคิดค่าใช้จ่ายวันโอน.pdf

    กฎ:
    - มรดก → ยกเว้น SBT เสมอ → อากรแสตมป์ 0.5% (ไม่ว่าถือกี่ปี)
    - ให้โดยเสน่หา → ถือ < 5 ปี = SBT, ถือ > 5 ปี = อากร
    - ซื้อมาเอง (บุคคล) → ถือ ≤ 5 ปี + ชื่อในทะเบียนบ้าน < 1 ปี = SBT
                          → ถือ > 5 ปี หรือ ชื่อในทะเบียน ≥ 1 ปี = อากร
    - นิติบุคคล → ถือ ≤ 5 ปี = SBT, ถือ > 5 ปี (สินทรัพย์ถาวร) = อากร

    Returns:
        (TaxChoice, เหตุผล)
    """
    # มรดก: ยกเว้น SBT เสมอ
    if acquisition_type == AcquisitionType.INHERITED:
        return TaxChoice.STAMP, "มรดก → ยกเว้น SBT เสมอ (ไม่ว่าถือกี่ปี) เสียอากรแสตมป์ 0.5%"

    # ให้โดยเสน่หา: ดูตามปีถือครองอย่างเดียว
    if acquisition_type == AcquisitionType.GIFT:
        if holding_years <= SBT_HOLDING_YEAR_THRESHOLD:
            return (
                TaxChoice.SBT,
                f"ให้โดยเสน่หา + ถือ {holding_years} ปี (≤ 5 ปี) → SBT 3.3%"
            )
        return (
            TaxChoice.STAMP,
            f"ให้โดยเสน่หา + ถือ {holding_years} ปี (> 5 ปี) → อากรแสตมป์ 0.5%"
        )

    # ซื้อมาเอง (บุคคล)
    if seller_type == SellerType.INDIVIDUAL:
        # ต้องเข้าทั้ง 2 เงื่อนไขถึงเสีย SBT:
        # 1) ถือ ≤ 5 ปี
        # 2) ชื่อในทะเบียนบ้าน < 1 ปี
        long_holding = holding_years > SBT_HOLDING_YEAR_THRESHOLD
        long_residency = (
            years_in_household_registration >= HOUSEHOLD_REGISTRATION_THRESHOLD_YEARS
        )

        if long_holding or long_residency:
            reason_parts = []
            if long_holding:
                reason_parts.append(f"ถือครอง {holding_years} ปี > 5 ปี")
            if long_residency:
                reason_parts.append(
                    f"ชื่อในทะเบียนบ้าน {years_in_household_registration} ปี ≥ 1 ปี"
                )
            return (
                TaxChoice.STAMP,
                "ซื้อมาเอง + " + " หรือ ".join(reason_parts) + " → อากรแสตมป์ 0.5%"
            )

        return (
            TaxChoice.SBT,
            f"ซื้อมาเอง + ถือ {holding_years} ปี ≤ 5 ปี + "
            f"ทะเบียนบ้าน {years_in_household_registration} ปี < 1 ปี → SBT 3.3%"
        )

    # นิติบุคคล: ดูปีถือครองอย่างเดียว
    if holding_years <= SBT_HOLDING_YEAR_THRESHOLD:
        return TaxChoice.SBT, f"นิติบุคคล + ถือ {holding_years} ปี ≤ 5 ปี → SBT 3.3%"
    return TaxChoice.STAMP, f"นิติบุคคล + ถือ {holding_years} ปี > 5 ปี → อากรแสตมป์ 0.5%"


def calculate_sbt(
    appraisal_price: Decimal,
    sale_price: Decimal,
) -> tuple[Decimal, str]:
    """
    คำนวณ SBT 3.3% × MAX(ราคาขาย, ราคาประเมิน)

    Business Rule: ระบบใช้ MAX สำหรับทุก calculation (conservative estimate)

    Returns:
        (sbt_amount, formula_text)
    """
    base = max_decimal(sale_price, appraisal_price)
    formula = f"3.3% × MAX(ราคาขาย, ราคาประเมิน) = 3.3% × {base:,.2f}"
    return round_money(base * SBT_EFFECTIVE_RATE), formula


def calculate_stamp_duty(
    appraisal_price: Decimal,
    sale_price: Decimal,
) -> tuple[Decimal, str]:
    """
    คำนวณอากรแสตมป์ 0.5% × MAX(ราคาขาย, ราคาประเมิน)

    Business Rule: ระบบใช้ MAX สำหรับทุก calculation (conservative estimate)

    Returns:
        (stamp_amount, formula_text)
    """
    base = max_decimal(sale_price, appraisal_price)
    formula = f"0.5% × MAX(ราคาขาย, ราคาประเมิน) = 0.5% × {base:,.2f}"
    return round_money(base * STAMP_DUTY_RATE), formula


# ============================================================================
# Main orchestrator
# ============================================================================

def calculate_transfer_costs(inp: TransferCalcInput) -> TransferCalcResult:
    """
    คำนวณค่าใช้จ่ายวันโอนทั้งหมด (Workflow 1)

    Args:
        inp: TransferCalcInput

    Returns:
        TransferCalcResult พร้อม breakdown ทุกรายการ + audit trail
    """
    warnings: list[str] = []

    # --- จำนวนปีถือครอง ---
    holding_years = calculate_holding_years(inp.acquisition_year, inp.sale_year)

    # --- 1. ค่าธรรมเนียมโอน — ใช้ MAX(ขาย, ประเมิน) ---
    transfer_fee = calculate_transfer_fee(inp.appraisal_price, inp.sale_price)
    tax_base_max = max_decimal(inp.sale_price, inp.appraisal_price)

    # --- 2. ค่าคำขอ + พยาน ---
    fixed_fee = REQUEST_WITNESS_TOTAL

    # --- 3. WHT ---
    if inp.seller_type == SellerType.INDIVIDUAL:
        wht_detail = calculate_wht_individual(
            appraisal_price=inp.appraisal_price,
            sale_price=inp.sale_price,
            acquisition_type=inp.acquisition_type,
            holding_years=holding_years,
            is_in_bangkok_metro=inp.is_in_bangkok_metro,
            has_intent_to_trade=inp.has_intent_to_trade,
        )
        if wht_detail.cap_applied:
            warnings.append(
                f"WHT ถูกจำกัดด้วยเพดาน 20% ของราคาขาย "
                f"(ก่อนเพดาน {wht_detail.total_tax_before_cap:,.2f}, "
                f"หลังเพดาน {wht_detail.final_tax:,.2f})"
            )
    else:  # CORPORATE
        wht_detail = calculate_wht_corporate(inp.sale_price, inp.appraisal_price)

    # --- 4. ตัดสินใจ SBT vs อากรแสตมป์ ---
    tax_choice, tax_reason = decide_sbt_or_stamp(
        seller_type=inp.seller_type,
        acquisition_type=inp.acquisition_type,
        holding_years=holding_years,
        years_in_household_registration=inp.years_in_household_registration,
    )

    if tax_choice == TaxChoice.SBT:
        sbt_amount, sbt_formula = calculate_sbt(inp.appraisal_price, inp.sale_price)
        stamp_amount = Decimal("0")
        stamp_formula = ""
    else:
        sbt_amount = Decimal("0")
        sbt_formula = ""
        stamp_amount, stamp_formula = calculate_stamp_duty(inp.appraisal_price, inp.sale_price)

    # --- 5. ค่าจดจำนอง (ถ้ามี) ---
    mortgage_fee = Decimal("0")
    if inp.has_mortgage:
        mortgage_fee = calculate_mortgage_fee(inp.mortgage_amount)

    # --- รวบรวม line items ---
    line_items: list[CostLineItem] = [
        CostLineItem(
            code="transfer_fee",
            description="ค่าธรรมเนียมการโอน",
            formula=f"2% × MAX(ราคาขาย, ราคาประเมิน) = 2% × {tax_base_max:,.2f}",
            amount=transfer_fee,
            rule_ref="แนวคิดค่าใช้จ่ายวันโอน.pdf",
        ),
        CostLineItem(
            code="request_witness",
            description="ค่าคำขอ + พยาน",
            formula="5 + 20",
            amount=fixed_fee,
            rule_ref="แนวคิดค่าใช้จ่ายวันโอน.pdf",
        ),
        CostLineItem(
            code="wht",
            description=(
                "ภาษีเงินได้หัก ณ ที่จ่าย (นิติบุคคล)"
                if inp.seller_type == SellerType.CORPORATE
                else "ภาษีเงินได้หัก ณ ที่จ่าย (บุคคลธรรมดา)"
            ),
            formula=(
                f"1% × MAX({inp.sale_price:,.2f}, {inp.appraisal_price:,.2f})"
                if inp.seller_type == SellerType.CORPORATE
                else f"ตามขั้นบันได × {holding_years} ปี"
            ),
            amount=wht_detail.final_tax,
            rule_ref="ป.100/2543 ข้อ 6",
        ),
    ]

    if tax_choice == TaxChoice.SBT:
        line_items.append(CostLineItem(
            code="sbt",
            description="ภาษีธุรกิจเฉพาะ (รวมภาษีท้องถิ่น)",
            formula=sbt_formula,
            amount=sbt_amount,
            rule_ref="formcal4.asp + การคำนวณภาษีธุรกิจเฉพาะ.pdf",
        ))
    else:
        line_items.append(CostLineItem(
            code="stamp_duty",
            description="อากรแสตมป์",
            formula=stamp_formula,
            amount=stamp_amount,
            rule_ref="formcal5.asp + การคำนวณอากรแสตมป์.pdf",
        ))

    if inp.has_mortgage and mortgage_fee > 0:
        line_items.append(CostLineItem(
            code="mortgage_fee",
            description="ค่าจดจำนอง",
            formula=f"1% × {inp.mortgage_amount:,.2f}",
            amount=mortgage_fee,
            rule_ref="แนวคิดค่าใช้จ่ายวันโอน.pdf",
        ))

    # --- รวมยอด ---
    total_cost = sum(li.amount for li in line_items)

    return TransferCalcResult(
        appraisal_price=inp.appraisal_price,
        sale_price=inp.sale_price,
        holding_years=holding_years,
        line_items=line_items,
        tax_choice=tax_choice,
        tax_choice_reason=tax_reason,
        wht_detail=wht_detail,
        total_cost=round_money(total_cost),
        warnings=warnings,
        engine_version=ENGINE_VERSION,
        tax_config_version=TAX_CONFIG_VERSION,
    )
