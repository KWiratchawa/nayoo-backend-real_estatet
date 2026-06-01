"""Calculation endpoints - WF1 (transfer) + WF2 (leaseback)"""
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.tax_engine.models import (
    AcquisitionType, SellerType, CorporateAssetType,
    TransferCalcInput, LeasebackCalcInput,
)
from app.tax_engine.wf1_transfer import calculate_transfer_costs
from app.tax_engine.wf2_leaseback import calculate_leaseback_costs

router = APIRouter()


class TransferRequest(BaseModel):
    """WF1: ค่าใช้จ่ายวันโอน"""
    seller_type: str  # "individual" | "corporate"
    acquisition_type: str  # "bought" | "inherited" | "gift"
    corporate_asset_type: Optional[str] = None  # "general" | "fixed_asset" (เฉพาะ corporate)
    acquisition_year: int
    sale_year: int
    years_in_household_registration: int = 0
    is_in_bangkok_metro: bool = False
    sale_price: float
    appraisal_price: float
    has_mortgage: bool = False
    mortgage_amount: float = 0
    has_intent_to_trade: bool = False


class LeasebackRequest(BaseModel):
    """WF2: ค่าใช้จ่ายขายฝาก"""
    seller_type: str
    acquisition_type: str
    corporate_asset_type: Optional[str] = None
    acquisition_year: int
    sale_year: int
    years_in_household_registration: int = 0
    is_in_bangkok_metro: bool = False
    repo_price: float
    expected_market_price: float
    appraisal_price: float
    interest_rate_monthly: float = 0.0125
    advance_interest_months: int = 3
    total_term_months: int = 9
    outstanding_debts: float = 0
    has_intent_to_trade: bool = False


@router.post("/transfer")
async def calculate_transfer(req: TransferRequest):
    """WF1: คำนวณค่าใช้จ่ายวันโอน"""
    try:
        result = calculate_transfer_costs(TransferCalcInput(
            seller_type=SellerType(req.seller_type),
            acquisition_type=AcquisitionType(req.acquisition_type),
            corporate_asset_type=CorporateAssetType(req.corporate_asset_type) if req.corporate_asset_type else None,
            acquisition_year=req.acquisition_year,
            sale_year=req.sale_year,
            years_in_household_registration=req.years_in_household_registration,
            is_in_bangkok_metro=req.is_in_bangkok_metro,
            sale_price=Decimal(str(req.sale_price)),
            appraisal_price=Decimal(str(req.appraisal_price)),
            has_mortgage=req.has_mortgage,
            mortgage_amount=Decimal(str(req.mortgage_amount)),
            has_intent_to_trade=req.has_intent_to_trade,
        ))
        return result.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/leaseback")
async def calculate_leaseback(req: LeasebackRequest):
    """WF2: คำนวณค่าใช้จ่ายขายฝาก"""
    try:
        result = calculate_leaseback_costs(LeasebackCalcInput(
            seller_type=SellerType(req.seller_type),
            acquisition_type=AcquisitionType(req.acquisition_type),
            corporate_asset_type=CorporateAssetType(req.corporate_asset_type) if req.corporate_asset_type else None,
            acquisition_year=req.acquisition_year,
            sale_year=req.sale_year,
            years_in_household_registration=req.years_in_household_registration,
            is_in_bangkok_metro=req.is_in_bangkok_metro,
            repo_price=Decimal(str(req.repo_price)),
            expected_market_price=Decimal(str(req.expected_market_price)),
            appraisal_price=Decimal(str(req.appraisal_price)),
            interest_rate_monthly=Decimal(str(req.interest_rate_monthly)),
            advance_interest_months=req.advance_interest_months,
            total_term_months=req.total_term_months,
            outstanding_debts=Decimal(str(req.outstanding_debts)),
            has_intent_to_trade=req.has_intent_to_trade,
        ))
        return result.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e))
