"""Tool interfaces and abstract protocols for CRM retrieval and persistence adapters."""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from app.models.client import CRMClientData
from app.models.review import ReviewRecord


class ToolError(Exception):
    """Base exception for external tool failures."""
    pass


class CRMTimeoutError(ToolError):
    """Raised when CRM API call times out."""
    pass


class CRMUnavailableError(ToolError):
    """Raised when CRM service is unreachable or returns 5xx."""
    pass


class CRMClientNotFoundError(ToolError):
    """Raised when client ID is not found in the CRM system."""
    pass


@runtime_checkable
class CRMToolInterface(Protocol):
    """Protocol defining the contract for retrieving client context from a CRM."""

    async def get_client_profile(
        self,
        client_id: str,
        timeout: Optional[float] = None,
        simulate_failure: bool = False,
        simulate_timeout: bool = False
    ) -> CRMClientData:
        """Fetch client profile data from CRM with retry and timeout guarantees."""
        ...

    async def health_check(self) -> bool:
        """Verify CRM connectivity."""
        ...


@runtime_checkable
class StorageInterface(Protocol):
    """Protocol defining the contract for persistent historical storage and reviews."""

    def save_analysis_summary(
        self,
        client_id: str,
        session_id: str,
        summary_data: Dict[str, Any]
    ) -> None:
        """Persist a client analysis summary with timestamp."""
        ...

    def get_client_history(
        self,
        client_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve historical summaries for a specific client."""
        ...

    def save_review(self, review: ReviewRecord) -> None:
        """Persist a human review audit record."""
        ...

    def get_reviews_for_client(self, client_id: str) -> List[ReviewRecord]:
        """Retrieve all review decisions associated with a client."""
        ...

    def get_review_for_finding(self, finding_id: str) -> Optional[ReviewRecord]:
        """Retrieve human review decision for a specific finding if one exists."""
        ...

    def prune_old_records(self, retention_days: int) -> int:
        """Prune records older than retention threshold. Returns count deleted."""
        ...
