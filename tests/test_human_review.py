"""Tests for HumanReviewService: approve, reject, and override workflows."""

from app.models.anomaly import SeverityLevel
from app.models.review import ReviewDecision, ReviewRequest
from app.services.review_service import HumanReviewService


def test_human_review_approve(test_review_service: HumanReviewService):
    req = ReviewRequest(
        decision=ReviewDecision.APPROVE,
        reviewer_id="ADV_401",
        reviewer_notes="Customer verified invoice."
    )
    record = test_review_service.submit_review("finding_1", "client_1", req)

    assert record.finding_id == "finding_1"
    assert record.decision == ReviewDecision.APPROVE
    assert record.reviewer_id == "ADV_401"

    retrieved = test_review_service.get_review_status("finding_1")
    assert retrieved is not None
    assert retrieved.decision == ReviewDecision.APPROVE


def test_human_review_reject(test_review_service: HumanReviewService):
    req = ReviewRequest(
        decision=ReviewDecision.REJECT,
        reviewer_id="ADV_402",
        reviewer_notes="False positive caused by recurring annual fee."
    )
    record = test_review_service.submit_review("finding_2", "client_1", req)

    assert record.decision == ReviewDecision.REJECT
    assert record.reviewer_id == "ADV_402"


def test_human_review_override(test_review_service: HumanReviewService):
    req = ReviewRequest(
        decision=ReviewDecision.OVERRIDE,
        reviewer_id="COMPLIANCE_OFFICER",
        reviewer_notes="Elevated to CRITICAL due to unverified high-risk recipient.",
        override_severity=SeverityLevel.CRITICAL,
        override_explanation="Manual compliance intervention"
    )
    record = test_review_service.submit_review("finding_3", "client_2", req)

    assert record.decision == ReviewDecision.OVERRIDE
    assert record.override_details is not None
    assert record.override_details["override_severity"] == "CRITICAL"
    assert record.override_details["override_explanation"] == "Manual compliance intervention"
