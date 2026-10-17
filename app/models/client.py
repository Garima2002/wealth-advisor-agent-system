"""Client domain models: transactions, portfolio holdings, CRM profile, and validation schemas."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    INVESTMENT = "investment"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    SPECULATIVE = "speculative"


class RawTransaction(BaseModel):
    """Raw un-normalized transaction from incoming JSON or external feed."""
    id: Optional[Any] = None
    date: Optional[Any] = None
    amount: Optional[Any] = None
    type: Optional[Any] = None
    category: Optional[Any] = None
    description: Optional[Any] = None
    merchant: Optional[Any] = None
    currency: Optional[Any] = "USD"


class Transaction(BaseModel):
    """Normalized, validated financial transaction."""
    id: str = Field(..., description="Unique transaction identifier")
    date: str = Field(..., description="ISO 8601 formatted date (YYYY-MM-DD)")
    amount: float = Field(..., description="Normalized positive amount value")
    type: TransactionType = Field(..., description="Transaction classification")
    category: str = Field(default="uncategorized", description="Spending or income category")
    description: Optional[str] = Field(default="", description="Transaction memo or details")
    merchant: Optional[str] = Field(default=None, description="Identified merchant or counterparty")
    currency: str = Field(default="USD", description="ISO currency code (USD, EUR, GBP, etc.)")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Amount must be non-negative in normalized form, got {v}")
        return round(float(v), 2)


class PortfolioHolding(BaseModel):
    """Client portfolio holding details."""
    asset_name: str
    asset_class: str = Field(..., description="e.g. EQUITIES, FIXED_INCOME, CASH, REAL_ESTATE, CRYPTO")
    current_value: float = Field(ge=0.0)
    allocation_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class CRMClientData(BaseModel):
    """Client profile and contextual metadata retrieved from CRM."""
    client_id: str
    name: str
    risk_profile: RiskProfile = RiskProfile.MODERATE
    monthly_income_declared: Optional[float] = None
    primary_advisor_id: Optional[str] = None
    kyc_status: str = "VERIFIED"
    last_interaction_date: Optional[str] = None
    notes: Optional[str] = None


class ClientFinancialProfile(BaseModel):
    """Consolidated client financial profile containing transactions, holdings, and CRM data."""
    client_id: str
    currency: str = "USD"
    transactions: List[Transaction] = Field(default_factory=list)
    portfolio: Optional[List[PortfolioHolding]] = None
    crm_context: Optional[CRMClientData] = None
    data_quality_warnings: List[str] = Field(default_factory=list)
    raw_unprocessed_records: int = 0
