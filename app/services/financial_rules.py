"""Deterministic, explainable financial anomaly detection rules engine."""

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dateutil.parser import parse as parse_date

from app.config import settings
from app.models.anomaly import AnomalyFinding, AnomalyType, SeverityLevel
from app.models.client import ClientFinancialProfile, RiskProfile, Transaction, TransactionType


def generate_finding_id(client_id: str, anomaly_type: str, tx_ids: List[str], observed: Any) -> str:
    """Generate a stable, deterministic finding ID."""
    sorted_txs = ",".join(sorted(tx_ids))
    raw_key = f"{client_id}:{anomaly_type}:{sorted_txs}:{str(observed)}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


class FinancialRulesEngine:
    """Deterministic financial anomaly calculation engine with explainable rules."""

    def __init__(
        self,
        large_tx_threshold: float = settings.ANOMALY_LARGE_TX_THRESHOLD,
        category_multiplier: float = settings.ANOMALY_CATEGORY_MULTIPLIER,
        category_min_samples: int = settings.ANOMALY_CATEGORY_MIN_SAMPLES,
        spending_spike_ratio: float = settings.ANOMALY_SPENDING_SPIKE_RATIO,
        duplicate_window_hours: int = settings.ANOMALY_DUPLICATE_WINDOW_HOURS,
        portfolio_concentration_threshold: float = settings.PORTFOLIO_CONCENTRATION_THRESHOLD,
    ):
        self.large_tx_threshold = large_tx_threshold
        self.category_multiplier = category_multiplier
        self.category_min_samples = category_min_samples
        self.spending_spike_ratio = spending_spike_ratio
        self.duplicate_window_hours = duplicate_window_hours
        self.portfolio_concentration_threshold = portfolio_concentration_threshold

    def evaluate(self, profile: ClientFinancialProfile) -> List[AnomalyFinding]:
        """Run all deterministic financial rules against the normalized client profile."""
        findings: List[AnomalyFinding] = []

        # 1. Evaluate transactions
        if profile.transactions:
            findings.extend(self._check_large_transactions(profile.client_id, profile.transactions))
            findings.extend(self._check_category_outliers(profile.client_id, profile.transactions))
            findings.extend(self._check_spending_spikes(profile.client_id, profile.transactions))
            findings.extend(self._check_duplicate_candidates(profile.client_id, profile.transactions))

        # 2. Evaluate portfolio if present
        if profile.portfolio:
            findings.extend(self._check_portfolio_risks(profile))

        return findings

    def _check_large_transactions(self, client_id: str, transactions: List[Transaction]) -> List[AnomalyFinding]:
        """Flag single transactions that exceed the configured absolute threshold."""
        findings = []
        for tx in transactions:
            if tx.type == TransactionType.EXPENSE and tx.amount >= self.large_tx_threshold:
                finding_id = generate_finding_id(
                    client_id,
                    AnomalyType.LARGE_TRANSACTION_ABSOLUTE.value,
                    [tx.id],
                    tx.amount
                )
                severity = SeverityLevel.HIGH if tx.amount >= self.large_tx_threshold * 2 else SeverityLevel.MEDIUM
                findings.append(
                    AnomalyFinding(
                        finding_id=finding_id,
                        anomaly_type=AnomalyType.LARGE_TRANSACTION_ABSOLUTE,
                        severity=severity,
                        relevant_transaction_ids=[tx.id],
                        observed_value=f"${tx.amount:,.2f}",
                        comparison_baseline=f"${self.large_tx_threshold:,.2f} (configured threshold)",
                        explanation=(
                            f"Transaction {tx.id} of ${tx.amount:,.2f} at '{tx.merchant or tx.category}' "
                            f"exceeds the absolute threshold of ${self.large_tx_threshold:,.2f}."
                        ),
                        limitations="Rule evaluates single transaction magnitude only; legitimate capital purchases or tax payments may trigger this rule; does not prove fraud or misconduct.",
                        recommended_verification="Verify invoice or vendor contract with the client to confirm authorization and tax classification."
                    )
                )
        return findings

    def _check_category_outliers(self, client_id: str, transactions: List[Transaction]) -> List[AnomalyFinding]:
        """Flag transactions exceeding N times category baseline mean when sufficient sample size exists."""
        findings = []
        category_expenses: Dict[str, List[Transaction]] = defaultdict(list)

        for tx in transactions:
            if tx.type == TransactionType.EXPENSE:
                category_expenses[tx.category.lower()].append(tx)

        for cat, tx_list in category_expenses.items():
            # Avoid statistical bias on tiny samples
            if len(tx_list) < self.category_min_samples:
                continue

            for tx in tx_list:
                # Leave-one-out baseline: evaluate candidate against other transactions in category
                other_amounts = [t.amount for t in tx_list if t.id != tx.id]
                mean_baseline = sum(other_amounts) / len(other_amounts) if other_amounts else tx.amount
                threshold = mean_baseline * self.category_multiplier

                if tx.amount > threshold and tx.amount > 100.0:  # Ignore trivial sub-$100 amounts
                    finding_id = generate_finding_id(
                        client_id,
                        AnomalyType.CATEGORY_SPENDING_OUTLIER.value,
                        [tx.id],
                        tx.amount
                    )
                    findings.append(
                        AnomalyFinding(
                            finding_id=finding_id,
                            anomaly_type=AnomalyType.CATEGORY_SPENDING_OUTLIER,
                            severity=SeverityLevel.MEDIUM,
                            relevant_transaction_ids=[tx.id],
                            observed_value=f"${tx.amount:,.2f}",
                            comparison_baseline=f"Category '{cat}' baseline mean: ${mean_baseline:,.2f} ({len(other_amounts)} prior observations)",
                            explanation=(
                                f"Transaction {tx.id} (${tx.amount:,.2f}) is {round(tx.amount / mean_baseline, 1)}x "
                                f"the historical category baseline mean of ${mean_baseline:,.2f} for '{cat}'."
                            ),
                            limitations="Requires minimum 3 observations; periodic bulk purchasing or annual subscriptions can naturally elevate category variance; does not prove fraud or misconduct.",
                            recommended_verification="Check whether the transaction represents an annual subscription, bulk order, or one-off equipment expenditure."
                        )
                    )
        return findings

    def _check_spending_spikes(self, client_id: str, transactions: List[Transaction]) -> List[AnomalyFinding]:
        """Compare latest monthly spending against baseline monthly spending when historical baseline is available."""
        findings = []
        monthly_totals: Dict[str, float] = defaultdict(float)
        monthly_tx_ids: Dict[str, List[str]] = defaultdict(list)

        for tx in transactions:
            if tx.type == TransactionType.EXPENSE:
                month_key = tx.date[:7]  # YYYY-MM
                monthly_totals[month_key] += tx.amount
                monthly_tx_ids[month_key].append(tx.id)

        # Need at least 2 distinct months to establish a comparison baseline
        if len(monthly_totals) < 2:
            return findings

        sorted_months = sorted(monthly_totals.keys())
        latest_month = sorted_months[-1]
        baseline_months = sorted_months[:-1]

        baseline_spending = [monthly_totals[m] for m in baseline_months]
        avg_baseline = sum(baseline_spending) / len(baseline_spending)
        latest_spending = monthly_totals[latest_month]

        if avg_baseline > 0 and (latest_spending / avg_baseline) >= self.spending_spike_ratio:
            ratio = round(latest_spending / avg_baseline, 2)
            finding_id = generate_finding_id(
                client_id,
                AnomalyType.MONTHLY_SPENDING_SPIKE.value,
                [latest_month],
                latest_spending
            )
            findings.append(
                AnomalyFinding(
                    finding_id=finding_id,
                    anomaly_type=AnomalyType.MONTHLY_SPENDING_SPIKE,
                    severity=SeverityLevel.HIGH if ratio >= 2.0 else SeverityLevel.MEDIUM,
                    relevant_transaction_ids=monthly_tx_ids[latest_month][:10],
                    observed_value=f"${latest_spending:,.2f} in {latest_month}",
                    comparison_baseline=f"Historical monthly baseline: ${avg_baseline:,.2f} ({len(baseline_months)} prior months)",
                    explanation=(
                        f"Spending in {latest_month} (${latest_spending:,.2f}) surged by {round((ratio - 1) * 100)}% "
                        f"compared to the prior baseline average of ${avg_baseline:,.2f}."
                    ),
                    limitations="Evaluates aggregate monthly outflow; seasonal holiday spending or planned renovations may account for the spike.",
                    recommended_verification="Review major outflow transactions for the month with the client to determine if the spike is recurring or transient."
                )
            )
        return findings

    def _check_duplicate_candidates(self, client_id: str, transactions: List[Transaction]) -> List[AnomalyFinding]:
        """Identify potential duplicate charges (identical amount & merchant/desc within 48h)."""
        findings = []
        expenses = [t for t in transactions if t.type == TransactionType.EXPENSE]

        # Sort chronologically
        try:
            sorted_expenses = sorted(expenses, key=lambda t: parse_date(t.date))
        except Exception:
            sorted_expenses = expenses

        seen_pairs = set()

        for i in range(len(sorted_expenses)):
            for j in range(i + 1, len(sorted_expenses)):
                t1 = sorted_expenses[i]
                t2 = sorted_expenses[j]

                # Match amount
                if abs(t1.amount - t2.amount) > 0.01:
                    continue

                # Match merchant or description
                m1 = (t1.merchant or t1.description or "").strip().lower()
                m2 = (t2.merchant or t2.description or "").strip().lower()
                if not m1 or not m2 or m1 != m2:
                    continue

                # Check time delta
                try:
                    d1 = parse_date(t1.date)
                    d2 = parse_date(t2.date)
                    delta_hours = abs((d2 - d1).total_seconds()) / 3600.0
                except Exception:
                    delta_hours = 0.0

                if delta_hours <= self.duplicate_window_hours:
                    pair_key = tuple(sorted([t1.id, t2.id]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    finding_id = generate_finding_id(
                        client_id,
                        AnomalyType.DUPLICATE_TRANSACTION.value,
                        [t1.id, t2.id],
                        t1.amount
                    )
                    findings.append(
                        AnomalyFinding(
                            finding_id=finding_id,
                            anomaly_type=AnomalyType.DUPLICATE_TRANSACTION,
                            severity=SeverityLevel.MEDIUM,
                            relevant_transaction_ids=[t1.id, t2.id],
                            observed_value=f"Two charges of ${t1.amount:,.2f} to '{t1.merchant or t1.description}' within {round(delta_hours, 1)}h",
                            comparison_baseline="Expected single charge for identical vendor within 48-hour window",
                            explanation=(
                                f"Transactions {t1.id} and {t2.id} share identical amount (${t1.amount:,.2f}) "
                                f"and merchant ('{t1.merchant or t1.description}') within {round(delta_hours, 1)} hours."
                            ),
                            limitations="Legitimate repeated purchases (e.g., daily transit passes or double coffee orders) may match this pattern.",
                            recommended_verification="Check with client and merchant billing statement to confirm whether this represents an accidental duplicate billing."
                        )
                    )
        return findings

    def _check_portfolio_risks(self, profile: ClientFinancialProfile) -> List[AnomalyFinding]:
        """Evaluate portfolio risk signals only when portfolio holding data exists."""
        findings = []
        portfolio = profile.portfolio or []
        if not portfolio:
            return findings

        total_val = sum(h.current_value for h in portfolio)
        if total_val <= 0:
            return findings

        # 1. Asset class concentration
        class_totals: Dict[str, float] = defaultdict(float)
        for h in portfolio:
            class_totals[h.asset_class.upper()] += h.current_value

        for asset_class, val in class_totals.items():
            pct = val / total_val
            if pct >= self.portfolio_concentration_threshold:
                finding_id = generate_finding_id(
                    profile.client_id,
                    AnomalyType.PORTFOLIO_CONCENTRATION_RISK.value,
                    [asset_class],
                    round(pct, 2)
                )
                findings.append(
                    AnomalyFinding(
                        finding_id=finding_id,
                        anomaly_type=AnomalyType.PORTFOLIO_CONCENTRATION_RISK,
                        severity=SeverityLevel.HIGH,
                        relevant_transaction_ids=[],
                        observed_value=f"{round(pct * 100, 1)}% in {asset_class} (${val:,.2f} of ${total_val:,.2f})",
                        comparison_baseline=f"Maximum recommended concentration: {round(self.portfolio_concentration_threshold * 100)}%",
                        explanation=(
                            f"Asset class '{asset_class}' constitutes {round(pct * 100, 1)}% of total portfolio value, "
                            f"exceeding the concentration guideline of {round(self.portfolio_concentration_threshold * 100)}%."
                        ),
                        limitations="Concentrated positions may be deliberate (e.g. founder equity or specialized mandate).",
                        recommended_verification="Discuss diversification strategy, hedging possibilities, and liquidity requirements with the client."
                    )
                )

        # 2. Risk profile mismatch if CRM data is available
        if profile.crm_context and profile.crm_context.risk_profile:
            crm_risk = profile.crm_context.risk_profile
            equity_pct = class_totals.get("EQUITIES", 0.0) / total_val

            if crm_risk == RiskProfile.CONSERVATIVE and equity_pct > 0.50:
                finding_id = generate_finding_id(
                    profile.client_id,
                    AnomalyType.RISK_PROFILE_MISMATCH.value,
                    ["EQUITIES", "CONSERVATIVE"],
                    round(equity_pct, 2)
                )
                findings.append(
                    AnomalyFinding(
                        finding_id=finding_id,
                        anomaly_type=AnomalyType.RISK_PROFILE_MISMATCH,
                        severity=SeverityLevel.HIGH,
                        relevant_transaction_ids=[],
                        observed_value=f"{round(equity_pct * 100, 1)}% Equities allocation",
                        comparison_baseline="Declared CRM Risk Profile: CONSERVATIVE (target equity <= 40%)",
                        explanation=(
                            f"Client declared a CONSERVATIVE risk profile in CRM, but holding equity exposure is {round(equity_pct * 100, 1)}%, "
                            "exceeding typical conservative tolerance."
                        ),
                        limitations="Market appreciation may have caused portfolio drift; recent client risk appetite updates may not be reflected in CRM.",
                        recommended_verification="Conduct an updated suitability assessment and rebalancing consultation."
                    )
                )

        return findings
