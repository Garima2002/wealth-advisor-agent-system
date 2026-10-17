"""FastAPI dependency injection providers."""

from functools import lru_cache
from typing import Annotated
from fastapi import Depends

from app.agents.analyzer import AnalyzerAgent
from app.agents.data_fetcher import DataFetcherAgent
from app.agents.insight import InsightAgent
from app.agents.orchestrator import OrchestratorAgent
from app.config import settings
from app.memory.session_memory import SessionMemoryStore
from app.memory.sqlite_memory import SQLiteMemoryStore
from app.services.financial_rules import FinancialRulesEngine
from app.services.review_service import HumanReviewService
from app.tools.interfaces import CRMToolInterface, StorageInterface
from app.tools.mock_crm import MockCRMAdapter


@lru_cache()
def get_storage() -> StorageInterface:
    """Singleton instance of persistent SQLite storage."""
    return SQLiteMemoryStore(db_path=settings.SQLITE_DB_PATH)


@lru_cache()
def get_session_store() -> SessionMemoryStore:
    """Singleton instance of in-memory short-term session store."""
    return SessionMemoryStore()


@lru_cache()
def get_crm_tool() -> CRMToolInterface:
    """CRM adapter instance (mock implementation with configurable bounds)."""
    return MockCRMAdapter(
        default_timeout=settings.CRM_TIMEOUT_SECONDS,
        max_retries=settings.CRM_MAX_RETRIES,
        backoff_factor=settings.CRM_RETRY_BACKOFF_FACTOR
    )


@lru_cache()
def get_rules_engine() -> FinancialRulesEngine:
    """Financial anomaly rules engine."""
    return FinancialRulesEngine()


def get_data_fetcher(
    crm_tool: Annotated[CRMToolInterface, Depends(get_crm_tool)]
) -> DataFetcherAgent:
    """DataFetcherAgent dependency."""
    return DataFetcherAgent(crm_tool=crm_tool)


def get_analyzer(
    rules_engine: Annotated[FinancialRulesEngine, Depends(get_rules_engine)]
) -> AnalyzerAgent:
    """AnalyzerAgent dependency."""
    return AnalyzerAgent(rules_engine=rules_engine)


def get_insight_agent() -> InsightAgent:
    """InsightAgent dependency."""
    return InsightAgent()


def get_orchestrator(
    data_fetcher: Annotated[DataFetcherAgent, Depends(get_data_fetcher)],
    analyzer: Annotated[AnalyzerAgent, Depends(get_analyzer)],
    insight_agent: Annotated[InsightAgent, Depends(get_insight_agent)],
    session_store: Annotated[SessionMemoryStore, Depends(get_session_store)],
    storage: Annotated[StorageInterface, Depends(get_storage)],
) -> OrchestratorAgent:
    """OrchestratorAgent dependency wired with all specialized agents and stores."""
    return OrchestratorAgent(
        data_fetcher=data_fetcher,
        analyzer=analyzer,
        insight_agent=insight_agent,
        session_store=session_store,
        storage=storage,
    )


def get_review_service(
    storage: Annotated[StorageInterface, Depends(get_storage)]
) -> HumanReviewService:
    """HumanReviewService dependency."""
    return HumanReviewService(storage=storage)
