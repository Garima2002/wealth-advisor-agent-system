"""Short-term session memory tracking workflow state, agent execution traces, and intermediate artifacts."""

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.anomaly import AnomalyFinding
from app.models.api import FinancialSummary
from app.models.client import ClientFinancialProfile
from app.models.insights import AdvisoryInsight


class ExecutionTrace(dict):
    """Execution step record."""
    agent: str
    stage: str
    duration_ms: float
    status: str
    notes: Optional[str]


class SessionContext:
    """Encapsulates short-term state for a single analysis workflow execution."""

    def __init__(self, client_id: str, session_id: Optional[str] = None):
        self.session_id: str = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self.client_id: str = client_id
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.workflow_stage: str = "INITIALIZED"
        self.traces: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.partial_result: bool = False
        self.crm_status: str = "UNKNOWN"

        # Intermediate data artifacts
        self.normalized_profile: Optional[ClientFinancialProfile] = None
        self.financial_summary: Optional[FinancialSummary] = None
        self.anomalies: List[AnomalyFinding] = []
        self.insights: List[AdvisoryInsight] = []

    def add_trace(
        self,
        agent: str,
        stage: str,
        duration_ms: float,
        status: str = "SUCCESS",
        notes: Optional[str] = None,
    ) -> None:
        """Record an agent execution step for observability."""
        self.traces.append({
            "agent": agent,
            "stage": stage,
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_warning(self, warning: str) -> None:
        """Add a data quality or execution warning."""
        if warning not in self.warnings:
            self.warnings.append(warning)

    def add_error(self, error: str) -> None:
        """Record a non-fatal or fatal error message."""
        self.errors.append(error)

    def set_stage(self, stage: str) -> None:
        """Update current workflow stage."""
        self.workflow_stage = stage

    def mark_partial(self, reason: str) -> None:
        """Flag that workflow completed with partial results due to a failed dependency."""
        self.partial_result = True
        self.add_warning(f"Partial result mode enabled: {reason}")


class SessionMemoryStore:
    """Thread-safe in-memory store for active session contexts."""

    def __init__(self, max_active_sessions: int = 500):
        self._sessions: Dict[str, SessionContext] = {}
        self._lock = threading.Lock()
        self.max_active_sessions = max_active_sessions

    def create_session(self, client_id: str, session_id: Optional[str] = None) -> SessionContext:
        """Initialize and register a new session."""
        session = SessionContext(client_id=client_id, session_id=session_id)
        with self._lock:
            if len(self._sessions) >= self.max_active_sessions:
                # Evict oldest session
                oldest_key = next(iter(self._sessions))
                self._sessions.pop(oldest_key, None)
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Retrieve an active session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        """Delete a session from memory."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def clear(self) -> None:
        """Clear all active sessions (primarily for test resets)."""
        with self._lock:
            self._sessions.clear()
