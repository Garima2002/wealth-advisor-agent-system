"""OrchestratorAgent: Coordinates the end-to-end multi-agent workflow, state, fallbacks, and responses."""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.agents.analyzer import AnalyzerAgent
from app.agents.base import BaseAgent
from app.agents.data_fetcher import DataFetcherAgent
from app.agents.insight import InsightAgent
from app.logging_config import correlation_id_ctx, get_logger
from app.memory.session_memory import SessionContext, SessionMemoryStore
from app.models.anomaly import ReviewStatus
from app.models.api import AnalysisResponse, AnalyzeRequest, FinancialSummary
from app.models.review import DECISION_TO_STATUS
from app.tools.interfaces import StorageInterface

logger = get_logger("agent.orchestrator")


class OrchestratorAgent(BaseAgent):
    """Central orchestrator coordinating specialized agents and handling partial fallbacks."""

    def __init__(
        self,
        data_fetcher: DataFetcherAgent,
        analyzer: AnalyzerAgent,
        insight_agent: InsightAgent,
        session_store: SessionMemoryStore,
        storage: StorageInterface,
    ):
        super().__init__(
            name="OrchestratorAgent",
            role_description="Coordinates end-to-end execution of data fetcher, analyzer, and insight agents."
        )
        self.data_fetcher = data_fetcher
        self.analyzer = analyzer
        self.insight_agent = insight_agent
        self.session_store = session_store
        self.storage = storage

    async def execute_analysis(
        self,
        request: AnalyzeRequest,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> AnalysisResponse:
        """Run the end-to-end multi-agent analysis pipeline."""
        start_time = time.perf_counter()
        req_id = correlation_id or f"req_{uuid.uuid4().hex[:8]}"
        correlation_id_ctx.set(req_id)

        session: SessionContext = self.session_store.create_session(
            client_id=request.client_id,
            session_id=session_id
        )

        logger.info(
            f"Orchestrator starting workflow for client {request.client_id} (session: {session.session_id})",
            extra={
                "agent": self.name,
                "stage": "workflow_start",
                "client_id": request.client_id,
                "correlation_id": req_id,
            }
        )

        try:
            # Stage 1: Data Ingestion & CRM Retrieval
            profile = await self.data_fetcher.run(
                client_id=request.client_id,
                raw_payload=request.client_profile,
                context=session,
                simulate_crm_failure=request.mock_crm_failure,
                simulate_crm_timeout=request.mock_crm_timeout,
            )

            # Stage 2: Financial Aggregations & Anomaly Detection
            summary, anomalies, risk_indicators = await self.analyzer.run(
                profile=profile,
                context=session
            )

            # Stage 3: Explainable Advisory Insight Generation
            insights = await self.insight_agent.run(
                profile=profile,
                summary=summary,
                anomalies=anomalies,
                risk_indicators=risk_indicators,
                context=session
            )

            # Stage 4: Sync with Human Review records if any exist in long-term storage
            review_counts = {
                ReviewStatus.PENDING.value: 0,
                ReviewStatus.APPROVED.value: 0,
                ReviewStatus.REJECTED.value: 0,
                ReviewStatus.OVERRIDDEN.value: 0,
            }

            for anomaly in anomalies:
                review_record = self.storage.get_review_for_finding(anomaly.finding_id)
                if review_record:
                    anomaly.review_status = DECISION_TO_STATUS.get(review_record.decision, ReviewStatus.PENDING)
                    anomaly.reviewer_id = review_record.reviewer_id
                    anomaly.reviewer_notes = review_record.reviewer_notes
                    anomaly.reviewed_at = review_record.timestamp
                    if review_record.override_details:
                        if review_record.override_details.get("override_severity"):
                            anomaly.severity = review_record.override_details["override_severity"]
                        if review_record.override_details.get("override_explanation"):
                            anomaly.explanation = review_record.override_details["override_explanation"]

                review_counts[anomaly.review_status.value] = review_counts.get(anomaly.review_status.value, 0) + 1

            # Stage 5: Long-Term Memory Persistence
            self.storage.save_analysis_summary(
                client_id=request.client_id,
                session_id=session.session_id,
                summary_data={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_income": summary.total_income,
                    "total_expenses": summary.total_expenses,
                    "net_cash_flow": summary.net_cash_flow,
                    "savings_rate_pct": summary.savings_rate_pct,
                    "anomaly_count": len(anomalies),
                    "partial_result": session.partial_result,
                    "category_breakdown": summary.category_breakdown,
                }
            )

            total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            session.set_stage("COMPLETED")

            logger.info(
                f"Orchestrator finished workflow for client {request.client_id} in {total_duration_ms}ms (partial: {session.partial_result})",
                extra={
                    "agent": self.name,
                    "stage": "workflow_complete",
                    "duration_ms": total_duration_ms,
                    "client_id": request.client_id,
                    "correlation_id": req_id,
                }
            )

            return AnalysisResponse(
                metadata={
                    "session_id": session.session_id,
                    "correlation_id": req_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": total_duration_ms,
                },
                client_id=request.client_id,
                financial_summary=summary,
                anomaly_findings=anomalies,
                risk_indicators=risk_indicators,
                actionable_insights=insights,
                data_quality_warnings=session.warnings,
                human_review_status=review_counts,
                system_status={
                    "partial_result": session.partial_result,
                    "crm_status": session.crm_status,
                    "execution_traces": session.traces,
                }
            )

        except Exception as e:
            total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            session.set_stage("FAILED")
            session.add_error(str(e))
            logger.error(
                f"Workflow execution failed: {e}",
                extra={
                    "agent": self.name,
                    "stage": "workflow_failed",
                    "duration_ms": total_duration_ms,
                    "error_category": type(e).__name__,
                    "client_id": request.client_id,
                    "correlation_id": req_id,
                },
                exc_info=True
            )
            raise e
