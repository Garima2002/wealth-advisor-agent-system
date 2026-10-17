"""Advisory insights models with strict separation between observed facts, hypotheses, and next steps."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class InsightCategory(str, Enum):
    CASH_FLOW = "CASH_FLOW"
    SAVINGS = "SAVINGS"
    ANOMALY_ALERT = "ANOMALY_ALERT"
    PORTFOLIO_RISK = "PORTFOLIO_RISK"
    DATA_INTEGRITY = "DATA_INTEGRITY"


class AdvisoryInsight(BaseModel):
    """Structured advisory insight separating facts, explanations, and non-discretionary next steps."""
    insight_id: str = Field(..., description="Unique insight identifier")
    category: InsightCategory = Field(..., description="Insight subject category")
    title: str = Field(..., description="Concise headline")
    observed_facts: List[str] = Field(
        ...,
        description="Factual, verifiable metrics observed directly in client records"
    )
    possible_explanations: List[str] = Field(
        ...,
        description="Plausible business/financial contexts explaining observed facts"
    )
    suggested_next_steps: List[str] = Field(
        ...,
        description="Actionable follow-up steps for the human advisor/client"
    )
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Confidence score based on completeness of underlying data"
    )
    disclaimer: str = Field(
        default="Advisory insight generated for analytical review only. Does not constitute binding investment advice, credit evaluation, or autonomous order routing.",
        description="Mandatory advisory disclaimer"
    )
