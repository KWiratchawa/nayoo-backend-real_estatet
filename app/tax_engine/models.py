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
    """ประเภทการได้มาซึ่งทรัพย์"""
    BOUGHT = "bought"            # ซื้อมาเอง / ได้มาทางอื่น
    INHERITED = "inherited"      # มรดก
    GIFT = "gift"                # ให้โดยเสน่หา


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
    SPLIT = "split"              # แบ่งกัน 50/50
    NEGOTIABLE = "negotiable"    # เจรจาตามดีล


class FeasibilityVerdict(str, Enum):
    GO = "go"
    NO_GO = "no_go"
    PENDING = "pending"


# ============================================================================
# Inputs
# ============================================================================

class LandArea(BaseModel):
    """พื้นที่ดิน ในหน่วยไทย"""
    rai: int = Field(0, ge=0, description="ไร่")
    ngan: int = Field(0, ge=0, lt=4, description="งาน (1 ไร่ = 4 งาน)")
    sq_wah: Decimal = Field(Decimal("0"), ge=0, lt=100, description="ตารางวา (1 งาน = 100 วา)")


class TransferCalcInput(BaseModel):
    """Input สำหรับ Workflow 1 (ค่าใช้จ่ายวันโอน)"""

    # ผู้ขาย
    seller_type: SellerType

    # การได้มา
    acquisition_type: AcquisitionType
    acquisition_year: int = Field(..., description="ปี พ.ศ. ที่ได้มา")
    sale_year: int = Field(..., description="ปี พ.ศ. ที่จะโอน")
    years_in_household_registration: int = Field(
        0, ge=0,
        description="จำนวนปีที่มีชื่อในทะเบียนบ้าน"
    )
    is_in_bangkok_metro: bool = Field(
        False,
        description="ทรัพย์อยู่ในเขต กทม./เทศบาล/พัทยา หรือไม่ (ใช้ตรวจ exemption 200K)"
    )

    # ราคา
    sale_price: Decimal = Field(..., gt=0, description="ราคาขายที่ตกลง")
    appraisal_price: Decimal = Field(..., gt=0, description="ราคาประเมินกรมธนารักษ์ (รวม)")

    # Optional
    has_mortgage: bool = False
    mortgage_amount: Decimal = Field(Decimal("0"), ge=0)
    has_intent_to_trade: bool = Field(
        False,
        description="มุ่งในทางการค้าหรือหากำไรหรือไม่ (default=False → ใช้เพดาน WHT 20%)"
    )


class LeasebackCalcInput(BaseModel):
    """Input สำหรับ Workflow 2 (ค่าใช้จ่ายขายฝาก)"""

    seller_type: SellerType = SellerType.INDIVIDUAL
    acquisition_type: AcquisitionType
    acquisition_year: int
    sale_year: int
    years_in_household_registration: int = 0
    is_in_bangkok_metro: bool = False
    has_intent_to_trade: bool = False

    # ขายฝาก
    repo_price: Decimal = Field(..., gt=0, description="ราคาขายฝากที่ตกลง")
    expected_market_price: Decimal = Field(..., gt=0, description="ราคาคาดว่าจะขายออก")
    appraisal_price: Decimal = Field(..., gt=0, description="ราคาประเมินกรมธนารักษ์")

    interest_rate_monthly: Decimal = Field(
        Decimal("0.0125"), ge=0, le=Decimal("0.0125"),
        description="อัตราดอกเบี้ยต่อเดือน (cap 1.25% ตามกฎหมาย)"
    )
    advance_interest_months: int = Field(3, ge=0, le=12)
    total_term_months: int = Field(9, ge=1, le=120)

    outstanding_debts: Decimal = Field(Decimal("0"), ge=0, description="ภาระหนี้ของผู้ขายฝาก")
    transfer_cost_paid_by: CostResponsibility = CostResponsibility.NEGOTIABLE


# ============================================================================
# Outputs
# ============================================================================

class CostLineItem(BaseModel):
    """รายการค่าใช้จ่าย 1 บรรทัด"""
    code: str = Field(..., description="รหัสรายการ เช่น transfer_fee, wht, sbt")
    description: str
    formula: str = Field("", description="สูตรที่ใช้คำนวณ")
    amount: Decimal
    cost_responsibility: Optional[CostResponsibility] = None
    rule_ref: str = Field("", description="อ้างอิงไฟล์ต้นทาง")


class WhtCalculationDetail(BaseModel):
    """รายละเอียดขั้นตอนคำนวณ WHT (สำหรับ audit trail)"""
    seller_type: SellerType
    holding_years: int
    income: Decimal = Field(..., description="1. เงินได้ (= ราคาประเมิน − exemption)")
    deduction_rate: Decimal
    deduction_amount: Decimal = Field(..., description="2. ค่าใช้จ่ายที่หัก")
    deduction_basis: str = Field(..., description="ฐานการคำนวณค่าใช้จ่าย")
    net_income: Decimal = Field(..., description="3. เงินได้สุทธิ")
    income_per_year: Decimal = Field(..., description="4. เงินได้เฉลี่ยต่อปี")
    tax_per_year: Decimal = Field(..., description="5. ภาษีต่อปี")
    total_tax_before_cap: Decimal = Field(..., description="6. ภาษีรวมก่อนใช้เพดาน")
    wht_cap: Decimal = Field(..., description="เพดาน 20% ของราคาขาย")
    cap_applied: bool = Field(..., description="ใช้เพดาน 20% หรือไม่")
    final_tax: Decimal = Field(..., description="ภาษีสุดท้ายที่ต้องชำระ")
    exemption_applied: Decimal = Field(Decimal("0"), description="ยกเว้น 200K (ถ้ามี)")


class TransferCalcResult(BaseModel):
    """ผลคำนวณ Workflow 1"""
    appraisal_price: Decimal
    sale_price: Decimal
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
    """ผลคำนวณ Workflow 2"""
    repo_price: Decimal
    expected_market_price: Decimal

    ltv_ratio: Decimal
    ltv_warning: bool

    # Leaseback specific
    advance_interest_amount: Decimal
    mouth_money_fee: Decimal
    redemption_amount: Decimal

    # ค่าใช้จ่ายวันโอน (embed WF1 result)
    transfer_costs: TransferCalcResult

    # Net to seller
    cash_received_before_transfer: Decimal
    net_proceeds_to_seller: Decimal

    # Feasibility
    outstanding_debts: Decimal
    covers_debts: bool
    feasibility_verdict: FeasibilityVerdict
    feasibility_reason: str

    warnings: list[str] = []
    engine_version: str
