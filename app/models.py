"""
tax_engine.models
~~~~~~~~~~~~~~~~~
Pydantic v2 models สำหรับ input/output ของ calculator
"""
from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class SellerType(str, Enum):
    """ประเภทผู้ขาย"""
    INDIVIDUAL = "individual"    # บุคคลธรรมดา
    CORPORATE = "corporate"      # นิติบุคคล


class AcquisitionType(str, Enum):
    """ประเภทการได้มาซึ่งทรัพย์ (สำหรับบุคคลธรรมดา)"""
    BOUGHT = "bought"            # ซื้อมาเอง / ได้มาทางอื่น
    INHERITED = "inherited"      # มรดก
    GIFT = "gift"                # ให้โดยเสน่หา


class CorporateAssetType(str, Enum):
    """ประเภททรัพย์ของนิติบุคคล (สำหรับ SBT decision)"""
    GENERAL = "general"            # ทรัพย์ทั่วไป/สินค้า → SBT เสมอ ไม่ว่าถือกี่ปี
    FIXED_ASSET = "fixed_asset"    # สินทรัพย์ถาวร (โรงงาน/สำนักงาน) → ถือ >5 ปี ยกเว้น SBT


class PropertyType(str, Enum):
    """ประเภททรัพย์"""
    LAND = "land"
    CONDO = "condo"
    HOUSE = "house"
    LAND_WITH_BUILDING = "land_with_building"


class TaxChoice(str, Enum):
    """ภาษี SBT หรืออากรแสตมป์ (เลือกอย่างใดอย่างหนึ่ง)"""
    SBT = "sbt"                  # ภาษีธุรกิจเฉพาะ 3.3%
    STAMP = "stamp"              # อากรแสตมป์ 0.5%


class CostResponsibility(str, Enum):
    """ใครรับผิดชอบค่าใช้จ่าย"""
    BUYER = "buyer"
    SELLER = "seller"
    SPLIT = "split"
    NEGOTIABLE = "negotiable"


class FeasibilityVerdict(str, Enum):
    GO = "go"
    NO_GO = "no_go"
    PENDING = "pending"


# ============================================================================
# Inputs
# ============================================================================

class LandArea(BaseModel):
    """พื้นที่ดิน ในหน่วยไทย"""
    rai: int = Field(0, ge=0)
    ngan: int = Field(0, ge=0, lt=4)
    sq_wah: Decimal = Field(Decimal("0"), ge=0, lt=100)


class TransferCalcInput(BaseModel):
    """Input สำหรับ Workflow 1 (ค่าใช้จ่ายวันโอน)"""
    seller_type: SellerType
    acquisition_type: AcquisitionType
    # NEW: ประเภททรัพย์นิติบุคคล — ใช้เมื่อ seller_type=CORPORATE
    corporate_asset_type: Optional[CorporateAssetType] = Field(
        None,
        description="ใช้เมื่อ seller_type=CORPORATE: GENERAL หรือ FIXED_ASSET"
    )
    acquisition_year: int
    sale_year: int
    years_in_household_registration: int = Field(0, ge=0)
    is_in_bangkok_metro: bool = False
    sale_price: Decimal = Field(..., gt=0)
    appraisal_price: Decimal = Field(..., gt=0)
    has_mortgage: bool = False
    mortgage_amount: Decimal = Field(Decimal("0"), ge=0)
    has_intent_to_trade: bool = Field(
        False,
        description="มุ่งค้าหากำไรหรือไม่ (default=False → ใช้เพดาน WHT 20%)"
    )


class LeasebackCalcInput(BaseModel):
    """Input สำหรับ Workflow 2 (ค่าใช้จ่ายขายฝาก)"""
    seller_type: SellerType = SellerType.INDIVIDUAL
    acquisition_type: AcquisitionType
    corporate_asset_type: Optional[CorporateAssetType] = None
    acquisition_year: int
    sale_year: int
    years_in_household_registration: int = 0
    is_in_bangkok_metro: bool = False
    has_intent_to_trade: bool = False

    repo_price: Decimal = Field(..., gt=0)
    expected_market_price: Decimal = Field(..., gt=0)
    appraisal_price: Decimal = Field(..., gt=0)

    interest_rate_monthly: Decimal = Field(
        Decimal("0.0125"), ge=0, le=Decimal("0.0125")
    )
    advance_interest_months: int = Field(3, ge=0, le=12)
    total_term_months: int = Field(9, ge=1, le=120)

    outstanding_debts: Decimal = Field(Decimal("0"), ge=0)
    transfer_cost_paid_by: CostResponsibility = CostResponsibility.NEGOTIABLE


# ============================================================================
# Outputs
# ============================================================================

class CostLineItem(BaseModel):
    code: str
    description: str
    formula: str = ""
    amount: Decimal
    cost_responsibility: Optional[CostResponsibility] = None
    rule_ref: str = ""


class WhtCalculationDetail(BaseModel):
    seller_type: SellerType
    holding_years: int
    income: Decimal
    deduction_rate: Decimal
    deduction_amount: Decimal
    deduction_basis: str
    net_income: Decimal
    income_per_year: Decimal
    tax_per_year: Decimal
    total_tax_before_cap: Decimal
    wht_cap: Decimal
    cap_applied: bool
    final_tax: Decimal
    exemption_applied: Decimal = Decimal("0")


class TransferCalcResult(BaseModel):
    appraisal_price: Decimal
    sale_price: Decimal
    tax_base: Decimal  # 🆕 v2.9: MAX(sale, appraisal) - ใช้คำนวณภาษีทุกฐาน
    holding_years: int
    line_items: list[CostLineItem]
    tax_choice: TaxChoice
    tax_choice_reason: str
    wht_detail: WhtCalculationDetail
    total_cost: Decimal
    warnings: list[str] = []
    engine_version: str
    tax_config_version: str


class LeasebackCalcResult(BaseModel):
    repo_price: Decimal
    expected_market_price: Decimal
    tax_base: Decimal  # 🆕 v2.9: MAX(repo, appraisal)
    sale_price: Decimal  # 🆕 v2.9: alias = repo_price (for FE compat)
    appraisal_price: Decimal  # 🆕 v2.9 (for FE compat)
    ltv_ratio: Decimal
    ltv_warning: bool
    advance_interest_amount: Decimal
    mouth_money_fee: Decimal
    redemption_amount: Decimal
    transfer_costs: TransferCalcResult
    cash_received_before_transfer: Decimal
    net_proceeds_to_seller: Decimal
    outstanding_debts: Decimal
    covers_debts: bool
    feasibility_verdict: FeasibilityVerdict
    feasibility_reason: str
    warnings: list[str] = []
    engine_version: str
