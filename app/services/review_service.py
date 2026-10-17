"""Human-in-the-loop review service for managing advisor oversight, approval, and override workflows."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.logging_config import get_logger
from app.models.anomaly import ReviewStatus, SeverityLevel
from app.models.review import ReviewDecision, ReviewRecord, ReviewRequest
from app.tools.interfaces import StorageInterface

logger = get_logger("services.human_review")


class HumanReviewService:
    """Service governing human approval, rejection, and overrides of flagged financial findings."""

    def __init__(self, storage: StorageInterface):
        self.storage = storage

    def submit_review(
        self,
        finding_id: str,
        client_id: str,
        request: ReviewRequest
    ) -> ReviewRecord:
        """Process a human review action and record audit log.

        STRICT SAFETY INVARIANT: This service NEVER initiates, triggers, or executes trades,
        asset transfers, account lockouts, or financial transactions.
        """
        logger.info(
            f"Processing human review for finding {finding_id} by reviewer {request.reviewer_id} with decision {request.decision.value}",
            extra={
                "agent": "HumanReviewService",
                "stage": "review_decision",
                "client_id": client_id,
            }
        )

        override_details = None
        if request.decision == ReviewDecision.OVERRIDE:
            override_details = {
                "override_severity": request.override_severity.value if request.override_severity else None,
                "override_explanation": request.override_explanation,
            }

        review_record = ReviewRecord(
            finding_id=finding_id,
            client_id=client_id,
            decision=request.decision,
            reviewer_id=request.reviewer_id,
            reviewer_notes=request.reviewer_notes,
            timestamp=datetime.now(timezone.utc).isoformat(),
            override_details=override_details,
        )

        # Persist audit record in long-term storage
        self.storage.save_review(review_record)
        return review_record

    def get_review_status(self, finding_id: str) -> Optional[ReviewRecord]:
        """Fetch human decision for a specific finding."""
        return self.storage.get_review_for_finding(finding_id)

    def get_client_reviews(self, client_id: str) -> List[ReviewRecord]:
        """Fetch all human review records for a given client."""
        return self.storage.get_reviews_for_client(client_id)
