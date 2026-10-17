"""Human-in-the-loop review models and audit records."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.models.anomaly import ReviewStatus, SeverityLevel


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    OVERRIDE = "OVERRIDE"


class ReviewRequest(BaseModel):
    """Payload submitted by a human advisor/compliance officer."""
    decision: ReviewDecision = Field(..., description="Review action: APPROVE, REJECT, or OVERRIDE")
    reviewer_id: str = Field(..., min_length=1, description="Identifier of the reviewer")
    reviewer_notes: str = Field(..., min_length=3, description="Detailed rationale for the decision")
    override_severity: Optional[SeverityLevel] = Field(
        default=None,
        description="Updated severity if decision is OVERRIDE"
    )
    override_explanation: Optional[str] = Field(
        default=None,
        description="Updated explanation if decision is OVERRIDE"
    )


class ReviewRecord(BaseModel):
    """Persistent audit record of a human review decision."""
    finding_id: str
    client_id: str
    decision: ReviewDecision
    reviewer_id: str
    reviewer_notes: str
    timestamp: str
    override_details: Optional[Dict[str, Any]] = None


DECISION_TO_STATUS = {
    ReviewDecision.APPROVE: ReviewStatus.APPROVED,
    ReviewDecision.REJECT: ReviewStatus.REJECTED,
    ReviewDecision.OVERRIDE: ReviewStatus.OVERRIDDEN,
}

