"""Tests for OrchestratorAgent: workflow coordination, stage tracing, and partial fallbacks."""

import asyncio
from app.agents.orchestrator import OrchestratorAgent
from app.models.anomaly import ReviewStatus, SeverityLevel
from app.models.api import AnalyzeRequest
from app.models.review import ReviewDecision, ReviewRecord
from app.memory.sqlite_memory import SQLiteMemoryStore


def test_orchestrator_full_workflow_coordination(
    test_orchestrator: OrchestratorAgent,
    sample_normal_data: dict
):
    request = AnalyzeRequest(client_id="client_001", client_profile=sample_normal_data)
    response = asyncio.run(test_orchestrator.execute_analysis(request))

    assert response.client_id == "client_001"
    assert response.financial_summary.total_income == 25000.0
    assert response.financial_summary.total_expenses == 6815.75
    assert response.system_status["partial_result"] is False
    assert response.system_status["crm_status"] == "CONNECTED"

    # Traces must contain stages from DataFetcher, Analyzer, and Insight agents
    traces = response.system_status["execution_traces"]
    agents_recorded = {t["agent"] for t in traces}
    assert "DataFetcherAgent" in agents_recorded
    assert "AnalyzerAgent" in agents_recorded
    assert "InsightAgent" in agents_recorded


def test_orchestrator_partial_fallback_crm_failure(
    test_orchestrator: OrchestratorAgent,
    sample_normal_data: dict
):
    request = AnalyzeRequest(
        client_id="client_001",
        client_profile=sample_normal_data,
        mock_crm_failure=True
    )
    response = asyncio.run(test_orchestrator.execute_analysis(request))

    # Workflow must complete successfully, marking partial result
    assert response.system_status["partial_result"] is True
    assert response.system_status["crm_status"] == "FAILED"
    assert len(response.data_quality_warnings) > 0
    assert response.financial_summary.transaction_count > 0


def test_orchestrator_merges_human_reviews_from_storage(
    test_orchestrator: OrchestratorAgent,
    test_storage: SQLiteMemoryStore,
    sample_anomalous_data: dict
):
    # Pre-populate a human review for the first finding
    req = AnalyzeRequest(client_id="client_002", client_profile=sample_anomalous_data)
    initial_res = asyncio.run(test_orchestrator.execute_analysis(req))
    target_finding = initial_res.anomaly_findings[0]

    test_storage.save_review(
        ReviewRecord(
            finding_id=target_finding.finding_id,
            client_id="client_002",
            decision=ReviewDecision.APPROVE,
            reviewer_id="ADV_TEST",
            reviewer_notes="Approved during test",
            timestamp="2026-10-17T12:00:00Z"
        )
    )

    # Re-run analysis
    second_res = asyncio.run(test_orchestrator.execute_analysis(req))
    reviewed_finding = next(f for f in second_res.anomaly_findings if f.finding_id == target_finding.finding_id)

    assert reviewed_finding.review_status == ReviewStatus.APPROVED
    assert reviewed_finding.reviewer_id == "ADV_TEST"
    assert second_res.human_review_status[ReviewStatus.APPROVED.value] >= 1
