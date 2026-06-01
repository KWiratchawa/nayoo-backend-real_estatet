"""
tax_engine.wf1_transfer
~~~~~~~~~~~~~~~~~~~~~~~
Workflow 1: คำนวณค่าใช้จ่ายวันโอน

ครอบคลุม 6 cases:
นิติบุคคล (2 cases):
  1. ทรัพย์ทั่วไป/สินค้า (ไม่ว่าถือกี่ปี) หรือ สินทรัพย์ถาวร < 5 ปี → SBT 3.3%
  2. สินทรัพย์ถาวร ≥ 5 ปี → ยกเว้น SBT → อากรแสตมป์ 0.5%

บุคคลธรรมดา (4 cases):
  1. ซื้อมาเอง + ถือ <5 ปี และทะเบียนบ้าน <1 ปี → SBT 3.3%
  2. ซื้อมาเอง + ถือ ≥5 ปี หรือทะเบียนบ้าน ≥1 ปี → อากรแสตมป์ 0.5%
  3. มรดก (ไม่ว่าถือกี่ปี) → ยกเว้น SBT เสมอ → อากรแสตมป์ 0.5%
  4. ให้โดยเสน่หา → ถือ <5 ปี = SBT 3.3%, ≥5 ปี = อากรแสตมป์ 0.5%
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
    CorporateAssetType,
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


def calculate_transfer_fee(appraisal_price: Decimal, sale_price: Decimal) -> Decimal:
    base = max_decimal(sale_price, appraisal_price)
    return round_money(base * TRANSFER_FEE_RATE)


def calculate_mortgage_fee(mortgage_amount: Decimal) -> Decimal:
    return round_money(mortgage_amount * MORTGAGE_FEE_RATE)


def _get_deduction_rate_bought(holding_years: int) -> Decimal:
    if holding_years >= 8:
        return DEDUCTION_RATES_BY_HOLDING_YEAR[8]
    return DEDUCTION_RATES_BY_HOLDING_YEAR[max(holding_years, 1)]


def calculate_wht_individual(
    appraisal_price: Decimal,
    sale_price: Decimal,
    acquisition_type: AcquisitionType,
    holding_years: int,
    is_in_bangkok_metro: bool,
    has_intent_to_trade: bool,
) -> WhtCalculationDetail:
    """WHT บุคคลธรรมดา (ตาม ป.100/2543 ข้อ 6)"""
    exemption = Decimal("0")
    if acquisition_type in (AcquisitionType.INHERITED, AcquisitionType.GIFT):
        if not is_in_bangkok_metro:
            exemption = WHT_NON_BKK_EXEMPTION

    tax_base = max_decimal(sale_price, appraisal_price)
    income = max(Decimal("0"), tax_base - exemption)

    if acquisition_type in (AcquisitionType.INHERITED, AcquisitionType.GIFT):
        deduction_rate = INHERITED_DEDUCTION_RATE
        deduction_basis = "มรดก/ให้โดยเสน่หา หักเหมา 50%"
    else:
        deduction_rate = _get_deduction_rate_bought(max(holding_years, 1))
        deduction_basis = f"ซื้อมาเอง หักตามพ.ร.ฎ.165 ที่ {holding_years} ปี = {deduction_rate*100}%"

    deduction_amount = income * deduction_rate
    net_income = income - deduction_amount

    holding_for_calc = max(holding_years, 1)
    income_per_year = net_income / Decimal(holding_for_calc)

    tax_per_year = calculate_progressive_tax(income_per_year, WHT_REAL_ESTATE_BRACKETS)
    total_tax_before_cap = tax_per_year * Decimal(holding_for_calc)

    wht_cap = sale_price * WHT_CAP_RATE

    if has_intent_to_trade:
        final_tax = total_tax_before_cap
        cap_applied = False
    else:
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


def calculate_wht_corporate(
    sale_price: Decimal,
    appraisal_price: Decimal,
) -> WhtCalculationDetail:
    """WHT นิติบุคคล = 1% × MAX(ราคาขาย, ราคาประเมิน)"""
    base = max_decimal(sale_price, appraisal_price)
    tax = base * WHT_CORPORATE_RATE

    return WhtCalculationDetail(
        seller_type=SellerType.CORPORATE,
        holding_years=0,
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


def decide_sbt_or_stamp(
    seller_type: SellerType,
    acquisition_type: AcquisitionType,
    corporate_asset_type: CorporateAssetType | None,
    holding_years: int,
    years_in_household_registration: int,
) -> tuple[TaxChoice, str]:
    """
    ตัดสินใจ SBT vs อากรแสตมป์ (6 cases)

    นิติบุคคล:
      - ทรัพย์ทั่วไป/สินค้า → SBT เสมอ (ไม่ว่าถือกี่ปี)
      - สินทรัพย์ถาวร + ถือ < 5 ปี → SBT
      - สินทรัพย์ถาวร + ถือ ≥ 5 ปี → อากรแสตมป์

    บุคคลธรรมดา:
      - มรดก → อากรแสตมป์เสมอ (ไม่ว่าถือกี่ปี)
      - ให้โดยเสน่หา + ถือ < 5 ปี → SBT
      - ให้โดยเสน่หา + ถือ ≥ 5 ปี → อากรแสตมป์
      - ซื้อมาเอง + ถือ < 5 ปี และ ทะเบียนบ้าน < 1 ปี → SBT
      - ซื้อมาเอง + ถือ ≥ 5 ปี หรือ ทะเบียนบ้าน ≥ 1 ปี → อากรแสตมป์
    """
    # ============ นิติบุคคล ============
    if seller_type == SellerType.CORPORATE:
        # default: ถ้าไม่ระบุ → GENERAL (เก็บ SBT)
        asset_type = corporate_asset_type or CorporateAssetType.GENERAL

        if asset_type == CorporateAssetType.GENERAL:
            return (
                TaxChoice.SBT,
                f"นิติบุคคล + ทรัพย์ทั่วไป/สินค้า (ไม่ว่าถือกี่ปี) → SBT 3.3%"
            )

        # FIXED_ASSET (สินทรัพย์ถาวร)
        if holding_years < SBT_HOLDING_YEAR_THRESHOLD:
            return (
                TaxChoice.SBT,
                f"นิติบุคคล + สินทรัพย์ถาวร + ถือ {holding_years} ปี (< 5 ปี) → SBT 3.3%"
            )
        return (
            TaxChoice.STAMP,
            f"นิติบุคคล + สินทรัพย์ถาวร + ถือ {holding_years} ปี (≥ 5 ปี) → อากรแสตมป์ 0.5%"
        )

    # ============ บุคคลธรรมดา ============

    # มรดก: ยกเว้น SBT เสมอ
    if acquisition_type == AcquisitionType.INHERITED:
        return TaxChoice.STAMP, "มรดก → ยกเว้น SBT เสมอ → อากรแสตมป์ 0.5%"

    # ให้โดยเสน่หา
    if acquisition_type == AcquisitionType.GIFT:
        if holding_years < SBT_HOLDING_YEAR_THRESHOLD:
            return (
                TaxChoice.SBT,
                f"ให้โดยเสน่หา + ถือ {holding_years} ปี (< 5 ปี) → SBT 3.3%"
            )
        return (
            TaxChoice.STAMP,
            f"ให้โดยเสน่หา + ถือ {holding_years} ปี (≥ 5 ปี) → อากรแสตมป์ 0.5%"
        )

    # ซื้อมาเอง (BOUGHT)
    long_holding = holding_years >= SBT_HOLDING_YEAR_THRESHOLD
    long_residency = (
        years_in_household_registration >= HOUSEHOLD_REGISTRATION_THRESHOLD_YEARS
    )

    if long_holding or long_residency:
        reason_parts = []
        if long_holding:
            reason_parts.append(f"ถือครอง {holding_years} ปี ≥ 5 ปี")
        if long_residency:
            reason_parts.append(
                f"ทะเบียนบ้าน {years_in_household_registration} ปี ≥ 1 ปี"
            )
        return (
            TaxChoice.STAMP,
            "ซื้อมาเอง + " + " หรือ ".join(reason_parts) + " → อากรแสตมป์ 0.5%"
        )

    return (
        TaxChoice.SBT,
        f"ซื้อมาเอง + ถือ {holding_years} ปี < 5 ปี + "
        f"ทะเบียนบ้าน {years_in_household_registration} ปี < 1 ปี → SBT 3.3%"
    )


def calculate_sbt(appraisal_price: Decimal, sale_price: Decimal) -> tuple[Decimal, str]:
    base = max_decimal(sale_price, appraisal_price)
    formula = f"3.3% × MAX(ราคาขาย, ราคาประเมิน) = 3.3% × {base:,.2f}"
    return round_money(base * SBT_EFFECTIVE_RATE), formula


def calculate_stamp_duty(appraisal_price: Decimal, sale_price: Decimal) -> tuple[Decimal, str]:
    base = max_decimal(sale_price, appraisal_price)
    formula = f"0.5% × MAX(ราคาขาย, ราคาประเมิน) = 0.5% × {base:,.2f}"
    return round_money(base * STAMP_DUTY_RATE), formula


def calculate_transfer_costs(inp: TransferCalcInput) -> TransferCalcResult:
    """Orchestrator คำนวณค่าใช้จ่ายวันโอน"""
    warnings: list[str] = []
    holding_years = calculate_holding_years(inp.acquisition_year, inp.sale_year)
    transfer_fee = calculate_transfer_fee(inp.appraisal_price, inp.sale_price)
    tax_base_max = max_decimal(inp.sale_price, inp.appraisal_price)
    fixed_fee = REQUEST_WITNESS_TOTAL

    # WHT
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
    else:
        wht_detail = calculate_wht_corporate(inp.sale_price, inp.appraisal_price)

    # SBT vs Stamp
    tax_choice, tax_reason = decide_sbt_or_stamp(
        seller_type=inp.seller_type,
        acquisition_type=inp.acquisition_type,
        corporate_asset_type=inp.corporate_asset_type,
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

    # Mortgage
    mortgage_fee = Decimal("0")
    if inp.has_mortgage:
        mortgage_fee = calculate_mortgage_fee(inp.mortgage_amount)

    # Line items
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
        ))
    else:
        line_items.append(CostLineItem(
            code="stamp_duty",
            description="อากรแสตมป์",
            formula=stamp_formula,
            amount=stamp_amount,
        ))

    if inp.has_mortgage and mortgage_fee > 0:
        line_items.append(CostLineItem(
            code="mortgage_fee",
            description="ค่าจดจำนอง",
            formula=f"1% × {inp.mortgage_amount:,.2f}",
            amount=mortgage_fee,
        ))

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
