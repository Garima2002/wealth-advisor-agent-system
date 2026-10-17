"""InsightAgent: Generates structured, explainable advisory insights with strict fact/hypothesis separation."""

from typing import List

from app.agents.base import BaseAgent
from app.memory.session_memory import SessionContext
from app.models.anomaly import AnomalyFinding, AnomalyType, SeverityLevel
from app.models.api import FinancialSummary, RiskIndicator
from app.models.client import ClientFinancialProfile
from app.models.insights import AdvisoryInsight, InsightCategory


class InsightAgent(BaseAgent):
    """Specialized advisory insight agent producing explainable recommendations."""

    def __init__(self):
        super().__init__(
            name="InsightAgent",
            role_description="Transforms quantitative analysis into structured advisory insights."
        )

    async def run(
        self,
        profile: ClientFinancialProfile,
        summary: FinancialSummary,
        anomalies: List[AnomalyFinding],
        risk_indicators: List[RiskIndicator],
        context: SessionContext,
    ) -> List[AdvisoryInsight]:
        """Generate structured advisory insights."""
        return await self.execute_stage(
            "insight_generation",
            context,
            self._generate_insights,
            profile,
            summary,
            anomalies,
            risk_indicators,
            context,
        )

    async def _generate_insights(
        self,
        profile: ClientFinancialProfile,
        summary: FinancialSummary,
        anomalies: List[AnomalyFinding],
        risk_indicators: List[RiskIndicator],
        context: SessionContext,
    ) -> List[AdvisoryInsight]:
        insights: List[AdvisoryInsight] = []
        confidence_base = 0.85 if context.partial_result else 1.0

        # 1. Cash Flow & Liquidity Insight
        if summary.transaction_count > 0:
            top_category_text = ""
            if summary.category_breakdown:
                top_cat, top_amt = next(iter(summary.category_breakdown.items()))
                top_category_text = f"Top spending category is '{top_cat}' at ${top_amt:,.2f}."

            cf_facts = [
                f"Total income recorded: ${summary.total_income:,.2f}.",
                f"Total living and operational expenses: ${summary.total_expenses:,.2f}.",
                f"Net period cash flow: ${summary.net_cash_flow:,.2f} over {summary.transaction_count} transactions.",
            ]
            if top_category_text:
                cf_facts.append(top_category_text)

            if summary.net_cash_flow >= 0:
                cf_explanations = [
                    "Client maintains positive operating cash flow during the evaluated interval.",
                    "Discretionary expenditures remain within baseline operational margins.",
                ]
                cf_actions = [
                    "Assess whether surplus cash can be routed toward tax-advantaged savings or emergency liquidity.",
                    "Review recurring monthly subscriptions to optimize continuous discretionary outlay.",
                ]
            else:
                cf_explanations = [
                    "Expenditures exceeded gross inflows for the period, causing a cash deficit.",
                    "Outflow surge may be driven by seasonal, capital, or one-off lump-sum expenses.",
                ]
                cf_actions = [
                    "Conduct a detailed line-item expense review to isolate non-recurring vs ongoing expenditure.",
                    "Evaluate short-term cash reserves or buffer accounts to cover near-term operational deficits.",
                ]

            insights.append(
                AdvisoryInsight(
                    insight_id=f"ins_cf_{context.session_id[-6:]}",
                    category=InsightCategory.CASH_FLOW,
                    title=f"Cash Flow Trajectory: {'Surplus' if summary.net_cash_flow >= 0 else 'Deficit'} (${abs(summary.net_cash_flow):,.2f})",
                    observed_facts=cf_facts,
                    possible_explanations=cf_explanations,
                    suggested_next_steps=cf_actions,
                    confidence_score=confidence_base,
                )
            )

        # 2. Anomaly & Outlier Governance Insight
        if anomalies:
            critical_high = [a for a in anomalies if a.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)]
            anomaly_facts = [
                f"{len(anomalies)} total anomaly findings flagged across transactional and balance records.",
                f"{len(critical_high)} findings categorized as HIGH or CRITICAL severity.",
            ]
            for a in anomalies[:3]:
                anomaly_facts.append(f"[{a.anomaly_type.value}] {a.observed_value} - {a.explanation}")

            insights.append(
                AdvisoryInsight(
                    insight_id=f"ins_anom_{context.session_id[-6:]}",
                    category=InsightCategory.ANOMALY_ALERT,
                    title=f"Financial Outliers & Review Queue ({len(anomalies)} findings)",
                    observed_facts=anomaly_facts,
                    possible_explanations=[
                        "Flagged anomalies reflect mathematical and rule deviations; they do not establish fraud or unauthorized activity.",
                        "Spikes may be attributable to legitimate high-value purchases, vendor billing adjustments, or accounting timing.",
                    ],
                    suggested_next_steps=[
                        "Submit pending findings to the HumanReviewService for formal advisor adjudication.",
                        "Contact client or accounting controller to confirm verification artifacts for highlighted charges.",
                        "Never initiate account blocks or transaction freezes without corroborating evidence.",
                    ],
                    confidence_score=round(confidence_base * 0.95, 2),
                )
            )

        # 3. Portfolio & Risk Insight
        if profile.portfolio:
            portfolio_anomalies = [
                a for a in anomalies if a.anomaly_type in (
                    AnomalyType.PORTFOLIO_CONCENTRATION_RISK,
                    AnomalyType.RISK_PROFILE_MISMATCH
                )
            ]
            port_facts = [
                f"Portfolio contains {len(profile.portfolio)} tracked asset holdings totaling ${sum(h.current_value for h in profile.portfolio):,.2f}."
            ]
            if portfolio_anomalies:
                for pa in portfolio_anomalies:
                    port_facts.append(f"Observed: {pa.observed_value} vs {pa.comparison_baseline}")

            insights.append(
                AdvisoryInsight(
                    insight_id=f"ins_port_{context.session_id[-6:]}",
                    category=InsightCategory.PORTFOLIO_RISK,
                    title="Portfolio Asset Allocation & Risk Alignment",
                    observed_facts=port_facts,
                    possible_explanations=[
                        "Asset appreciation over time can cause allocation drift beyond initial target risk profiles.",
                        "Holdings may reflect concentrated employer equity compensation or targeted legacy investments.",
                    ],
                    suggested_next_steps=[
                        "Schedule an asset-allocation review to discuss potential diversification or rebalancing options.",
                        "Review current investor profile in CRM to verify whether risk tolerance remains accurate.",
                    ],
                    confidence_score=confidence_base,
                )
            )

        # 4. Data Quality & Coverage Insight (if any degradation)
        if context.warnings or context.partial_result:
            dq_facts = [
                f"Data quality warnings registered during processing: {len(context.warnings)}.",
                f"Partial execution status: {'ACTIVE (Dependency degraded)' if context.partial_result else 'INACTIVE'}.",
            ] + context.warnings[:3]

            insights.append(
                AdvisoryInsight(
                    insight_id=f"ins_dq_{context.session_id[-6:]}",
                    category=InsightCategory.DATA_INTEGRITY,
                    title="Data Completeness & Ingestion Integrity",
                    observed_facts=dq_facts,
                    possible_explanations=[
                        "Upstream mock CRM network latency or schema variances triggered fallback handling.",
                        "Input transactions may originate from disparate raw bank export formats.",
                    ],
                    suggested_next_steps=[
                        "Check upstream connectivity with CRM endpoint or mock provider.",
                        "Ensure raw data feeds supply standard ISO 8601 timestamps and non-negative expense values.",
                    ],
                    confidence_score=0.75,
                )
            )

        context.insights = insights
        return insights
