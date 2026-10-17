"""Tests for InsightAgent: explainable insights and fact/hypothesis separation."""

import asyncio
from app.agents.insight import InsightAgent
from app.memory.session_memory import SessionContext
from app.models.anomaly import AnomalyFinding, AnomalyType, SeverityLevel
from app.models.api import FinancialSummary, RiskIndicator
from app.models.client import ClientFinancialProfile
from app.models.insights import InsightCategory


def test_insight_agent_structure_and_disclaimer():
    agent = InsightAgent()
    context = SessionContext(client_id="client_test")

    profile = ClientFinancialProfile(client_id="client_test")
    summary = FinancialSummary(
        total_income=12000.0,
        total_expenses=4500.0,
        net_cash_flow=7500.0,
        savings_rate_pct=62.5,
        category_breakdown={"housing": 2500.0, "dining": 2000.0},
        transaction_count=20
    )
    anomalies = [
        AnomalyFinding(
            finding_id="f123",
            anomaly_type=AnomalyType.LARGE_TRANSACTION_ABSOLUTE,
            severity=SeverityLevel.HIGH,
            relevant_transaction_ids=["tx1"],
            observed_value="$6,000.00",
            comparison_baseline="$5,000.00",
            explanation="Transaction exceeds threshold",
            recommended_verification="Check with client invoice"
        )
    ]
    risks = [
        RiskIndicator(
            indicator_name="TEST_RISK",
            severity=SeverityLevel.MEDIUM,
            observed="Observed test risk",
            evidence="Evidence"
        )
    ]

    insights = asyncio.run(agent.run(profile, summary, anomalies, risks, context))

    assert len(insights) >= 2  # Cash flow insight + Anomaly insight

    cf_insight = next(i for i in insights if i.category == InsightCategory.CASH_FLOW)
    assert len(cf_insight.observed_facts) > 0
    assert len(cf_insight.possible_explanations) > 0
    assert len(cf_insight.suggested_next_steps) > 0

    # Ensure no automated trade language exists in suggested steps
    for ins in insights:
        for step in ins.suggested_next_steps:
            assert "execute buy" not in step.lower()
            assert "execute sell" not in step.lower()
            assert "transfer funds" not in step.lower()
        # Verify mandatory disclaimer
        assert "does not constitute binding investment advice" in ins.disclaimer.lower()


def test_insight_confidence_degradation_on_partial_result():
    agent = InsightAgent()
    context = SessionContext(client_id="client_test")
    context.mark_partial("CRM unavailable")

    profile = ClientFinancialProfile(client_id="client_test")
    summary = FinancialSummary(
        total_income=5000.0,
        total_expenses=4000.0,
        net_cash_flow=1000.0,
        savings_rate_pct=20.0,
        transaction_count=5
    )

    insights = asyncio.run(agent.run(profile, summary, [], [], context))
    cf_insight = next(i for i in insights if i.category == InsightCategory.CASH_FLOW)

    # In partial mode confidence score is adjusted downwards
    assert cf_insight.confidence_score < 1.0
