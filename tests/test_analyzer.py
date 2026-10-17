"""Tests for AnalyzerAgent and FinancialRulesEngine: calculations and anomaly rules."""

import asyncio
from app.agents.analyzer import AnalyzerAgent
from app.memory.session_memory import SessionContext
from app.models.anomaly import AnomalyType, SeverityLevel
from app.models.client import (
    ClientFinancialProfile,
    CRMClientData,
    PortfolioHolding,
    RiskProfile,
    Transaction,
    TransactionType,
)
from app.services.financial_rules import FinancialRulesEngine


def test_analyzer_financial_aggregations():
    agent = AnalyzerAgent()
    context = SessionContext(client_id="client_calc")

    txs = [
        Transaction(id="t1", date="2026-09-01", amount=10000.0, type=TransactionType.INCOME, category="salary"),
        Transaction(id="t2", date="2026-09-05", amount=3000.0, type=TransactionType.EXPENSE, category="rent"),
        Transaction(id="t3", date="2026-09-10", amount=500.0, type=TransactionType.EXPENSE, category="groceries"),
        Transaction(id="t4", date="2026-09-15", amount=500.0, type=TransactionType.EXPENSE, category="groceries"),
    ]
    profile = ClientFinancialProfile(client_id="client_calc", transactions=txs)

    summary, anomalies, risks = asyncio.run(agent.run(profile, context))

    assert summary.total_income == 10000.0
    assert summary.total_expenses == 4000.0
    assert summary.net_cash_flow == 6000.0
    assert summary.savings_rate_pct == 60.0
    assert summary.transaction_count == 4
    assert summary.category_breakdown == {"rent": 3000.0, "groceries": 1000.0}
    assert summary.period_start == "2026-09-01"
    assert summary.period_end == "2026-09-15"


def test_rule_large_transaction_threshold():
    engine = FinancialRulesEngine(large_tx_threshold=5000.0)
    txs = [
        Transaction(id="t1", date="2026-09-01", amount=4999.0, type=TransactionType.EXPENSE, category="electronics"),
        Transaction(id="t2", date="2026-09-02", amount=7500.0, type=TransactionType.EXPENSE, category="luxury"),
    ]
    profile = ClientFinancialProfile(client_id="test_client", transactions=txs)
    findings = engine.evaluate(profile)

    large_tx_findings = [f for f in findings if f.anomaly_type == AnomalyType.LARGE_TRANSACTION_ABSOLUTE]
    assert len(large_tx_findings) == 1
    assert large_tx_findings[0].relevant_transaction_ids == ["t2"]
    assert "$7,500.00" in large_tx_findings[0].observed_value
    assert "not prove fraud" in large_tx_findings[0].limitations.lower()


def test_rule_category_outlier_sufficient_samples_vs_insufficient():
    engine = FinancialRulesEngine(category_multiplier=3.0, category_min_samples=3)

    # Category with only 2 items: should NOT flag even if ratio is high (insufficient baseline)
    txs_insufficient = [
        Transaction(id="t1", date="2026-09-01", amount=50.0, type=TransactionType.EXPENSE, category="dining"),
        Transaction(id="t2", date="2026-09-02", amount=500.0, type=TransactionType.EXPENSE, category="dining"),
    ]
    profile_insufficient = ClientFinancialProfile(client_id="test_client", transactions=txs_insufficient)
    findings1 = engine.evaluate(profile_insufficient)
    assert not any(f.anomaly_type == AnomalyType.CATEGORY_SPENDING_OUTLIER for f in findings1)

    # Category with 3 items (sufficient sample): should flag outlier with leave-one-out baseline
    txs_sufficient = [
        Transaction(id="t1", date="2026-09-01", amount=50.0, type=TransactionType.EXPENSE, category="dining"),
        Transaction(id="t2", date="2026-09-02", amount=60.0, type=TransactionType.EXPENSE, category="dining"),
        Transaction(id="t3", date="2026-09-03", amount=600.0, type=TransactionType.EXPENSE, category="dining"),
    ]
    profile_sufficient = ClientFinancialProfile(client_id="test_client", transactions=txs_sufficient)
    findings2 = engine.evaluate(profile_sufficient)
    outliers = [f for f in findings2 if f.anomaly_type == AnomalyType.CATEGORY_SPENDING_OUTLIER]
    assert len(outliers) == 1
    assert outliers[0].relevant_transaction_ids == ["t3"]
    assert "not prove fraud" in outliers[0].limitations.lower()


def test_rule_duplicate_transaction_detection():
    engine = FinancialRulesEngine(duplicate_window_hours=48)
    txs = [
        Transaction(id="t1", date="2026-09-01", amount=120.0, type=TransactionType.EXPENSE, merchant="Acme SaaS", category="software"),
        Transaction(id="t2", date="2026-09-02", amount=120.0, type=TransactionType.EXPENSE, merchant="Acme SaaS", category="software"),
        # Different vendor, same amount: not a duplicate
        Transaction(id="t3", date="2026-09-02", amount=120.0, type=TransactionType.EXPENSE, merchant="Other Vendor", category="software"),
        # Same vendor, 10 days later: outside window, not a duplicate
        Transaction(id="t4", date="2026-09-15", amount=120.0, type=TransactionType.EXPENSE, merchant="Acme SaaS", category="software"),
    ]
    profile = ClientFinancialProfile(client_id="test_client", transactions=txs)
    findings = engine.evaluate(profile)

    duplicates = [f for f in findings if f.anomaly_type == AnomalyType.DUPLICATE_TRANSACTION]
    assert len(duplicates) == 1
    assert set(duplicates[0].relevant_transaction_ids) == {"t1", "t2"}


def test_rule_portfolio_concentration_and_risk_profile_mismatch():
    engine = FinancialRulesEngine(portfolio_concentration_threshold=0.60)
    holdings = [
        PortfolioHolding(asset_name="Tech ETF", asset_class="EQUITIES", current_value=80000.0),
        PortfolioHolding(asset_name="Treasury Bond", asset_class="FIXED_INCOME", current_value=20000.0),
    ]
    crm_context = CRMClientData(
        client_id="client_port",
        name="Conservative Investor",
        risk_profile=RiskProfile.CONSERVATIVE
    )
    profile = ClientFinancialProfile(
        client_id="client_port",
        portfolio=holdings,
        crm_context=crm_context
    )
    findings = engine.evaluate(profile)

    # Should flag 80% Equities concentration (> 60%)
    conc = [f for f in findings if f.anomaly_type == AnomalyType.PORTFOLIO_CONCENTRATION_RISK]
    assert len(conc) == 1
    assert "80.0% in EQUITIES" in conc[0].observed_value

    # Should flag risk mismatch (Conservative client with 80% equities)
    mismatch = [f for f in findings if f.anomaly_type == AnomalyType.RISK_PROFILE_MISMATCH]
    assert len(mismatch) == 1


def test_rule_no_portfolio_anomalies_when_portfolio_none():
    engine = FinancialRulesEngine()
    profile = ClientFinancialProfile(client_id="test_client", transactions=[], portfolio=None)
    findings = engine.evaluate(profile)

    # Must NOT hallucinate portfolio findings without data
    assert not any(f.anomaly_type in (
        AnomalyType.PORTFOLIO_CONCENTRATION_RISK,
        AnomalyType.RISK_PROFILE_MISMATCH
    ) for f in findings)
