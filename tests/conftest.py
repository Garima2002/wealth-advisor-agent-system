"""Pytest fixtures and configuration for Wealth Advisor Multi-Agent System."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.agents.analyzer import AnalyzerAgent
from app.agents.data_fetcher import DataFetcherAgent
from app.agents.insight import InsightAgent
from app.agents.orchestrator import OrchestratorAgent
from app.api.dependencies import (
    get_crm_tool,
    get_orchestrator,
    get_review_service,
    get_session_store,
    get_storage,
)
from app.api.main import create_app
from app.memory.session_memory import SessionMemoryStore
from app.memory.sqlite_memory import SQLiteMemoryStore
from app.services.financial_rules import FinancialRulesEngine
from app.services.review_service import HumanReviewService
from app.tools.mock_crm import MockCRMAdapter


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Provides a fresh isolated SQLite database file per test."""
    db_file = tmp_path / "test_wealth_advisor.db"
    return str(db_file)


@pytest.fixture
def test_storage(temp_db_path: str) -> SQLiteMemoryStore:
    """Isolated SQLite storage instance."""
    return SQLiteMemoryStore(db_path=temp_db_path)


@pytest.fixture
def test_session_store() -> SessionMemoryStore:
    """Isolated in-memory session store."""
    return SessionMemoryStore()


@pytest.fixture
def test_crm_tool() -> MockCRMAdapter:
    """Fast deterministic Mock CRM adapter."""
    return MockCRMAdapter(base_delay_seconds=0.001, default_timeout=0.2, max_retries=2, backoff_factor=0.01)


@pytest.fixture
def test_rules_engine() -> FinancialRulesEngine:
    """Rules engine instance with default thresholds."""
    return FinancialRulesEngine()


@pytest.fixture
def test_review_service(test_storage: SQLiteMemoryStore) -> HumanReviewService:
    """Review service connected to isolated storage."""
    return HumanReviewService(storage=test_storage)


@pytest.fixture
def test_orchestrator(
    test_crm_tool: MockCRMAdapter,
    test_rules_engine: FinancialRulesEngine,
    test_session_store: SessionMemoryStore,
    test_storage: SQLiteMemoryStore,
) -> OrchestratorAgent:
    """Fully assembled orchestrator agent."""
    data_fetcher = DataFetcherAgent(crm_tool=test_crm_tool)
    analyzer = AnalyzerAgent(rules_engine=test_rules_engine)
    insight_agent = InsightAgent()

    return OrchestratorAgent(
        data_fetcher=data_fetcher,
        analyzer=analyzer,
        insight_agent=insight_agent,
        session_store=test_session_store,
        storage=test_storage,
    )


@pytest.fixture
def sample_normal_data() -> dict:
    with open("data/sample_client_normal.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_anomalous_data() -> dict:
    with open("data/sample_client_anomalous.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_malformed_data() -> dict:
    with open("data/sample_client_malformed.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def api_client(
    test_storage: SQLiteMemoryStore,
    test_session_store: SessionMemoryStore,
    test_crm_tool: MockCRMAdapter,
    test_orchestrator: OrchestratorAgent,
    test_review_service: HumanReviewService,
) -> TestClient:
    """FastAPI test client configured with isolated fixtures."""
    app = create_app()

    app.dependency_overrides[get_storage] = lambda: test_storage
    app.dependency_overrides[get_session_store] = lambda: test_session_store
    app.dependency_overrides[get_crm_tool] = lambda: test_crm_tool
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator
    app.dependency_overrides[get_review_service] = lambda: test_review_service

    client = TestClient(app)
    return client
