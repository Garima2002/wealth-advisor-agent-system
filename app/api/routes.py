"""FastAPI router endpoints for analysis, sessions, client history, health, and reviews."""

from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status

from app.agents.orchestrator import OrchestratorAgent
from app.api.dependencies import (
    get_orchestrator,
    get_review_service,
    get_session_store,
    get_storage,
)
from app.memory.session_memory import SessionMemoryStore
from app.models.api import (
    AnalysisResponse,
    AnalyzeRequest,
    ClientHistoryItem,
    ClientHistoryResponse,
    ErrorResponse,
    HealthResponse,
)
from app.models.review import ReviewRecord, ReviewRequest
from app.services.review_service import HumanReviewService
from app.tools.interfaces import StorageInterface

router = APIRouter(tags=["Wealth Advisor Agent System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Liveness Probe",
    description="Returns service availability, timestamp, and version status."
)
async def health_check() -> HealthResponse:
    """Liveness probe for monitoring infrastructure."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_status="operational"
    )


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input data"},
        500: {"model": ErrorResponse, "description": "Internal processing failure"},
    },
    summary="Execute Financial Analysis Workflow",
    description="Ingests client data, fetches CRM context, detects anomalies, and generates advisory insights."
)
async def analyze_client(
    request: AnalyzeRequest,
    orchestrator: Annotated[OrchestratorAgent, Depends(get_orchestrator)],
    x_correlation_id: Optional[str] = Header(default=None, alias="X-Correlation-ID")
) -> AnalysisResponse:
    """Orchestrates multi-agent analysis for a given client."""
    try:
        response = await orchestrator.execute_analysis(
            request=request,
            correlation_id=x_correlation_id,
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis pipeline execution failed: {str(e)}"
        )


@router.get(
    "/sessions/{session_id}",
    summary="Retrieve Session Execution Trace",
    description="Fetches intermediate workflow state and agent traces from short-term memory."
)
async def get_session(
    session_id: str,
    session_store: Annotated[SessionMemoryStore, Depends(get_session_store)],
) -> Dict[str, Any]:
    """Retrieve short-term session state."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found in active session memory."
        )

    return {
        "session_id": session.session_id,
        "client_id": session.client_id,
        "created_at": session.created_at,
        "workflow_stage": session.workflow_stage,
        "crm_status": session.crm_status,
        "partial_result": session.partial_result,
        "warnings": session.warnings,
        "traces": session.traces,
    }


@router.get(
    "/clients/{client_id}/history",
    response_model=ClientHistoryResponse,
    summary="Retrieve Historical Summaries",
    description="Fetches client-scoped historical analysis runs from persistent long-term storage."
)
async def get_client_history(
    client_id: str,
    storage: Annotated[StorageInterface, Depends(get_storage)],
    limit: int = Query(default=50, ge=1, le=100)
) -> ClientHistoryResponse:
    """Retrieve historical summaries strictly scoped to the requesting client_id."""
    raw_history = storage.get_client_history(client_id=client_id, limit=limit)
    items = [
        ClientHistoryItem(
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            net_cash_flow=row["net_cash_flow"],
            total_income=row["total_income"],
            total_expenses=row["total_expenses"],
            anomaly_count=row["anomaly_count"],
            partial_result=row["partial_result"],
        )
        for row in raw_history
    ]
    return ClientHistoryResponse(
        client_id=client_id,
        count=len(items),
        records=items,
    )


@router.post(
    "/reviews/{finding_id}",
    response_model=ReviewRecord,
    status_code=status.HTTP_200_OK,
    summary="Submit Human Review Decision",
    description="Enables a human advisor or compliance officer to approve, reject, or override a flagged finding."
)
async def review_finding(
    finding_id: str,
    review_request: ReviewRequest,
    review_service: Annotated[HumanReviewService, Depends(get_review_service)],
    client_id: str = Query(..., description="Target client identifier for record scoping")
) -> ReviewRecord:
    """Record human-in-the-loop decision for an anomaly finding."""
    record = review_service.submit_review(
        finding_id=finding_id,
        client_id=client_id,
        request=review_request
    )
    return record
