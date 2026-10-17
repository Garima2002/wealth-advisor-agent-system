"""AnalyzerAgent: Computes financial summaries, evaluates deterministic anomaly rules, and flags risk signals."""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.agents.base import BaseAgent
from app.memory.session_memory import SessionContext
from app.models.anomaly import AnomalyFinding, AnomalyType, SeverityLevel
from app.models.api import FinancialSummary, RiskIndicator
from app.models.client import ClientFinancialProfile, TransactionType
from app.services.financial_rules import FinancialRulesEngine, generate_finding_id


class AnalyzerAgent(BaseAgent):
    """Specialized financial analysis and anomaly detection agent."""

    def __init__(self, rules_engine: Optional[FinancialRulesEngine] = None):
        super().__init__(
            name="AnalyzerAgent",
            role_description="Computes cash flow summaries and executes explainable anomaly rules."
        )
        self.rules_engine = rules_engine or FinancialRulesEngine()

    async def run(
        self,
        profile: ClientFinancialProfile,
        context: SessionContext
    ) -> Tuple[FinancialSummary, List[AnomalyFinding], List[RiskIndicator]]:
        """Run summary calculations and anomaly detection."""
        return await self.execute_stage(
            "financial_analysis",
            context,
            self._analyze,
            profile,
            context
        )

    async def _analyze(
        self,
        profile: ClientFinancialProfile,
        context: SessionContext
    ) -> Tuple[FinancialSummary, List[AnomalyFinding], List[RiskIndicator]]:
        txs = profile.transactions

        # 1. Compute Financial Aggregations
        total_income = 0.0
        total_expenses = 0.0
        category_breakdown: Dict[str, float] = defaultdict(float)
        dates: List[str] = []

        for tx in txs:
            dates.append(tx.date)
            if tx.type == TransactionType.INCOME:
                total_income += tx.amount
            elif tx.type == TransactionType.EXPENSE:
                total_expenses += tx.amount
                category_breakdown[tx.category] = round(
                    category_breakdown[tx.category] + tx.amount, 2
                )

        total_income = round(total_income, 2)
        total_expenses = round(total_expenses, 2)
        net_cash_flow = round(total_income - total_expenses, 2)

        savings_rate = None
        if total_income > 0:
            savings_rate = round((net_cash_flow / total_income) * 100.0, 2)

        sorted_dates = sorted(dates) if dates else []
        period_start = sorted_dates[0] if sorted_dates else None
        period_end = sorted_dates[-1] if sorted_dates else None

        summary = FinancialSummary(
            total_income=total_income,
            total_expenses=total_expenses,
            net_cash_flow=net_cash_flow,
            savings_rate_pct=savings_rate,
            category_breakdown=dict(sorted(category_breakdown.items(), key=lambda x: x[1], reverse=True)),
            period_start=period_start,
            period_end=period_end,
            transaction_count=len(txs),
        )
        context.financial_summary = summary

        # 2. Execute Deterministic Anomaly Rules
        anomalies = self.rules_engine.evaluate(profile)

        # 3. Add Data Quality Anomaly if any severe input defects were caught
        if profile.data_quality_warnings:
            future_or_negative = [
                w for w in profile.data_quality_warnings
                if "future date" in w.lower() or "negative amount" in w.lower()
            ]
            if future_or_negative:
                f_id = generate_finding_id(
                    profile.client_id,
                    AnomalyType.DATA_INTEGRITY.value,
                    ["DATA_QUALITY"],
                    len(future_or_negative)
                )
                anomalies.append(
                    AnomalyFinding(
                        finding_id=f_id,
                        anomaly_type=AnomalyType.DATA_INTEGRITY,
                        severity=SeverityLevel.LOW,
                        relevant_transaction_ids=[],
                        observed_value=f"{len(future_or_negative)} data normalization issues detected",
                        comparison_baseline="Clean, standardized transactional feed",
                        explanation=f"Data normalization adjusted inputs: {'; '.join(future_or_negative[:3])}",
                        limitations="Records were normalized automatically; verification ensures bookkeeping consistency.",
                        recommended_verification="Confirm bank feed export format and accounting ledger synchronization."
                    )
                )

        context.anomalies = anomalies

        # 4. Generate Risk Indicators
        risk_indicators = self._generate_risk_indicators(summary, anomalies, profile)

        return summary, anomalies, risk_indicators

    def _generate_risk_indicators(
        self,
        summary: FinancialSummary,
        anomalies: List[AnomalyFinding],
        profile: ClientFinancialProfile
    ) -> List[RiskIndicator]:
        """Derive actionable risk indicators from summaries and detected anomalies."""
        indicators: List[RiskIndicator] = []

        # Negative Cash Flow Risk
        if summary.net_cash_flow < 0:
            indicators.append(
                RiskIndicator(
                    indicator_name="NEGATIVE_NET_CASH_FLOW",
                    severity=SeverityLevel.HIGH,
                    observed=f"Net cash flow is -${abs(summary.net_cash_flow):,.2f}",
                    evidence=f"Total expenditures (${summary.total_expenses:,.2f}) exceed recorded income (${summary.total_income:,.2f})."
                )
            )
        elif summary.savings_rate_pct is not None and summary.savings_rate_pct < 10.0:
            indicators.append(
                RiskIndicator(
                    indicator_name="LOW_SAVINGS_RATE",
                    severity=SeverityLevel.MEDIUM,
                    observed=f"Savings rate is {summary.savings_rate_pct:.1f}%",
                    evidence="Savings rate is below the typical 15-20% wealth-building benchmark."
                )
            )

        # High Anomaly Volume Risk
        high_severity_anomalies = [a for a in anomalies if a.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)]
        if len(high_severity_anomalies) >= 2:
            indicators.append(
                RiskIndicator(
                    indicator_name="ELEVATED_ANOMALY_CONCENTRATION",
                    severity=SeverityLevel.HIGH,
                    observed=f"{len(high_severity_anomalies)} high/critical anomalies detected",
                    evidence=f"Identified multiple material anomalies requiring advisor review: {', '.join(a.anomaly_type.value for a in high_severity_anomalies)}."
                )
            )

        # Portfolio Concentration Risk Signal
        concentration_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.PORTFOLIO_CONCENTRATION_RISK]
        for ca in concentration_anomalies:
            indicators.append(
                RiskIndicator(
                    indicator_name="PORTFOLIO_CONCENTRATION",
                    severity=ca.severity,
                    observed=str(ca.observed_value),
                    evidence=ca.explanation
                )
            )

        return indicators
