"""Anomaly detection models, severity classifications, and review tracking schemas."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnomalyType(str, Enum):
    LARGE_TRANSACTION_ABSOLUTE = "LARGE_TRANSACTION_ABSOLUTE"
    CATEGORY_SPENDING_OUTLIER = "CATEGORY_SPENDING_OUTLIER"
    MONTHLY_SPENDING_SPIKE = "MONTHLY_SPENDING_SPIKE"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    MALFORMED_TRANSACTION = "MALFORMED_TRANSACTION"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    PORTFOLIO_CONCENTRATION_RISK = "PORTFOLIO_CONCENTRATION_RISK"
    RISK_PROFILE_MISMATCH = "RISK_PROFILE_MISMATCH"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    OVERRIDDEN = "OVERRIDDEN"


class AnomalyFinding(BaseModel):
    """Structured, explainable anomaly finding."""
    finding_id: str = Field(..., description="Stable deterministic hash or identifier for the finding")
    anomaly_type: AnomalyType = Field(..., description="Specific financial anomaly or data integrity issue")
    severity: SeverityLevel = Field(..., description="Risk or severity classification")
    relevant_transaction_ids: List[str] = Field(default_factory=list, description="IDs of transactions involved")
    observed_value: Any = Field(..., description="The observed value or pattern triggering the alert")
    comparison_baseline: Optional[Any] = Field(default=None, description="Baseline metric or expected range")
    explanation: str = Field(..., description="Explainable description of the detection logic")
    limitations: str = Field(
        default="Statistical/rule-based indicator only; does not prove fraud, misconduct, or unauthorized activity.",
        description="Explicit limitation of the rule"
    )
    recommended_verification: str = Field(
        ...,
        description="Concrete, actionable verification steps for the advisor or analyst"
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.PENDING,
        description="Human review status"
    )
    reviewer_id: Optional[str] = Field(default=None, description="ID of human reviewer if reviewed")
    reviewer_notes: Optional[str] = Field(default=None, description="Reviewer feedback or rationale")
    reviewed_at: Optional[str] = Field(default=None, description="ISO timestamp of review decision")
