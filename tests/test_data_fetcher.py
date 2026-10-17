"""Tests for DataFetcherAgent: validation, normalization, and CRM failure handling."""

import asyncio
from app.agents.data_fetcher import DataFetcherAgent
from app.memory.session_memory import SessionContext
from app.models.client import RiskProfile, TransactionType
from app.tools.mock_crm import MockCRMAdapter


def test_data_fetcher_normal_ingestion(test_crm_tool: MockCRMAdapter, sample_normal_data: dict):
    agent = DataFetcherAgent(crm_tool=test_crm_tool)
    context = SessionContext(client_id="client_001")

    profile = asyncio.run(
        agent.run(
            client_id="client_001",
            raw_payload=sample_normal_data,
            context=context
        )
    )

    assert profile.client_id == "client_001"
    assert len(profile.transactions) == len(sample_normal_data["transactions"])
    assert profile.crm_context is not None
    assert profile.crm_context.name == "[SYNTHETIC] Sarah Jenkins"
    assert profile.crm_context.risk_profile == RiskProfile.MODERATE
    assert context.crm_status == "CONNECTED"
    assert context.partial_result is False


def test_data_fetcher_malformed_and_edge_cases(test_crm_tool: MockCRMAdapter, sample_malformed_data: dict):
    agent = DataFetcherAgent(crm_tool=test_crm_tool)
    context = SessionContext(client_id="client_003")

    profile = asyncio.run(
        agent.run(
            client_id="client_003",
            raw_payload=sample_malformed_data,
            context=context
        )
    )

    # Negative amount should be converted to positive
    tx_m02 = next((t for t in profile.transactions if t.id == "tx_m02"), None)
    assert tx_m02 is not None
    assert tx_m02.amount == 150.0  # Normalized to positive

    # Unparseable date (tx_m04) and non-numeric amount (tx_m05) must be omitted
    assert not any(t.id == "tx_m04" for t in profile.transactions)
    assert not any(t.id == "tx_m05" for t in profile.transactions)

    # Warnings must contain future date and negative amount notices
    warning_text = " ".join(context.warnings)
    assert "future date" in warning_text.lower()
    assert "negative amount" in warning_text.lower()
    assert "malformed amount" in warning_text.lower()


def test_data_fetcher_crm_failure_graceful_degradation(test_crm_tool: MockCRMAdapter, sample_normal_data: dict):
    agent = DataFetcherAgent(crm_tool=test_crm_tool)
    context = SessionContext(client_id="client_001")

    profile = asyncio.run(
        agent.run(
            client_id="client_001",
            raw_payload=sample_normal_data,
            context=context,
            simulate_crm_failure=True
        )
    )

    assert profile.crm_context is None
    assert context.crm_status == "FAILED"
    assert context.partial_result is True
    assert any("CRM context unavailable" in w for w in context.warnings)
    # Transactions must still be fully ingested and available for downstream agents
    assert len(profile.transactions) > 0


def test_data_fetcher_crm_timeout_graceful_degradation(test_crm_tool: MockCRMAdapter, sample_normal_data: dict):
    agent = DataFetcherAgent(crm_tool=test_crm_tool)
    context = SessionContext(client_id="client_001")

    profile = asyncio.run(
        agent.run(
            client_id="client_001",
            raw_payload=sample_normal_data,
            context=context,
            simulate_crm_timeout=True
        )
    )

    assert profile.crm_context is None
    assert context.crm_status == "FAILED"
    assert context.partial_result is True
    assert any("CRM context unavailable" in w for w in context.warnings)
