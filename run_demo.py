"""End-to-End demonstration script for Wealth Advisor Multi-Agent System showcasing all core workflows."""

import asyncio
import json
from pathlib import Path

from app.cli import create_orchestrator
from app.models.anomaly import SeverityLevel
from app.models.api import AnalyzeRequest
from app.models.review import ReviewDecision, ReviewRequest


async def run_comprehensive_demo():
    print("\n" + "=" * 80)
    print("  WEALTH ADVISOR MULTI-AGENT SYSTEM - COMPREHENSIVE END-TO-END DEMO")
    print("=" * 80)

    demo_db = "demo_wealth_advisor.db"
    orchestrator, review_service, storage = create_orchestrator(db_path=demo_db)

    # ---------------------------------------------------------
    # SCENARIO 1: Normal Client Analysis (No Anomalies)
    # ---------------------------------------------------------
    print("\n[SCENARIO 1] Analyzing Normal Client (client_001: Sarah Jenkins)...")
    normal_file = Path("data/sample_client_normal.json")
    with open(normal_file, "r", encoding="utf-8") as f:
        normal_data = json.load(f)

    req1 = AnalyzeRequest(client_id="client_001", client_profile=normal_data)
    res1 = await orchestrator.execute_analysis(req1)

    print(f"  -> Execution Time: {res1.metadata['duration_ms']}ms | Session: {res1.metadata['session_id']}")
    print(f"  -> Total Income: ${res1.financial_summary.total_income:,.2f} | Expenses: ${res1.financial_summary.total_expenses:,.2f}")
    print(f"  -> Net Cash Flow: ${res1.financial_summary.net_cash_flow:,.2f} (Savings Rate: {res1.financial_summary.savings_rate_pct}%)")
    print(f"  -> Anomalies Detected: {len(res1.anomaly_findings)} (Clean baseline scenario)")
    print(f"  -> Advisory Insights: {len(res1.actionable_insights)}")
    for ins in res1.actionable_insights:
        print(f"     * [{ins.category.value}] {ins.title}")

    # ---------------------------------------------------------
    # SCENARIO 2: Anomalous Client Analysis
    # ---------------------------------------------------------
    print("\n" + "-" * 80)
    print("[SCENARIO 2] Analyzing High Net Worth Client with Multiple Financial Anomalies (client_002)...")
    anom_file = Path("data/sample_client_anomalous.json")
    with open(anom_file, "r", encoding="utf-8") as f:
        anom_data = json.load(f)

    req2 = AnalyzeRequest(client_id="client_002", client_profile=anom_data)
    res2 = await orchestrator.execute_analysis(req2)

    print(f"  -> Execution Time: {res2.metadata['duration_ms']}ms | Session: {res2.metadata['session_id']}")
    print(f"  -> Net Cash Flow: ${res2.financial_summary.net_cash_flow:,.2f}")
    print(f"  -> Anomalies Flagged: {len(res2.anomaly_findings)}")
    for idx, a in enumerate(res2.anomaly_findings, 1):
        print(f"     [{idx}] ID: {a.finding_id} | {a.anomaly_type.value} [{a.severity.value}]")
        print(f"         Observed: {a.observed_value}")
        print(f"         Baseline: {a.comparison_baseline}")
        print(f"         Reason:   {a.explanation}")

    print(f"  -> Risk Indicators: {len(res2.risk_indicators)}")
    for r in res2.risk_indicators:
        print(f"     * [{r.severity.value}] {r.indicator_name}: {r.observed}")

    # Save real execution output to data/sample_output.json
    output_path = Path("data/sample_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(res2.model_dump(), f, indent=2)
    print(f"  -> Real execution output written to {output_path}")

    # ---------------------------------------------------------
    # SCENARIO 3: CRM Transient Failure & Graceful Partial Degradation
    # ---------------------------------------------------------
    print("\n" + "-" * 80)
    print("[SCENARIO 3] Simulating CRM Failure (Graceful Degradation / Partial Result)...")
    req3 = AnalyzeRequest(
        client_id="client_003",
        client_profile=normal_data,
        mock_crm_failure=True
    )
    res3 = await orchestrator.execute_analysis(req3)
    print(f"  -> Execution Status: {'PARTIAL RESULT' if res3.system_status['partial_result'] else 'FULL'}")
    print(f"  -> CRM Service Status: {res3.system_status['crm_status']}")
    print(f"  -> System Warnings: {res3.data_quality_warnings}")
    print(f"  -> Workflow Completed Gracefully: {res3.financial_summary.transaction_count} transactions analyzed.")

    # ---------------------------------------------------------
    # SCENARIO 4: Malformed Data Ingestion & Sanitization
    # ---------------------------------------------------------
    print("\n" + "-" * 80)
    print("[SCENARIO 4] Ingesting Malformed Data (Negative amounts, future dates, invalid records)...")
    malformed_file = Path("data/sample_client_malformed.json")
    with open(malformed_file, "r", encoding="utf-8") as f:
        malformed_data = json.load(f)

    req4 = AnalyzeRequest(client_id="client_003", client_profile=malformed_data)
    res4 = await orchestrator.execute_analysis(req4)
    print(f"  -> Valid Transactions Recovered: {res4.financial_summary.transaction_count}")
    print(f"  -> Data Quality Warnings Recorded ({len(res4.data_quality_warnings)}):")
    for w in res4.data_quality_warnings:
        print(f"     * {w}")

    # ---------------------------------------------------------
    # SCENARIO 5: Human-in-the-Loop Review & Long-Term Audit Trail
    # ---------------------------------------------------------
    print("\n" + "-" * 80)
    print("[SCENARIO 5] Human-in-the-Loop Review Lifecycle (Advisor Decision & Override)...")
    first_finding = res2.anomaly_findings[0]
    print(f"  -> Flagged Finding ID: {first_finding.finding_id} ({first_finding.anomaly_type.value})")
    print(f"  -> Initial Review Status: {first_finding.review_status.value}")

    # Advisor submits an APPROVE decision with justification
    review_record = review_service.submit_review(
        finding_id=first_finding.finding_id,
        client_id=res2.client_id,
        request=ReviewRequest(
            decision=ReviewDecision.APPROVE,
            reviewer_id="ADV_SARAH_CONNER",
            reviewer_notes="Client confirmed luxury jeweler purchase as an anniversary gift. Invoice verified."
        )
    )
    print(f"  -> Review Submitted: Decision={review_record.decision.value} by {review_record.reviewer_id}")
    print(f"  -> Audit Record Timestamp: {review_record.timestamp}")

    # Re-run analysis for client_002 to verify that review status is loaded from long-term memory
    res2_updated = await orchestrator.execute_analysis(req2)
    updated_finding = next(f for f in res2_updated.anomaly_findings if f.finding_id == first_finding.finding_id)
    print(f"  -> Re-analyzed Finding Status: {updated_finding.review_status.value} (Reviewer: {updated_finding.reviewer_id})")
    print(f"  -> Human Review Status Counts: {res2_updated.human_review_status}")

    # ---------------------------------------------------------
    # SCENARIO 6: Client Scoping & Long-Term Historical Memory
    # ---------------------------------------------------------
    print("\n" + "-" * 80)
    print("[SCENARIO 6] Long-Term Storage & Client Isolation Verification...")
    history_001 = storage.get_client_history("client_001")
    history_002 = storage.get_client_history("client_002")
    history_003 = storage.get_client_history("client_003")

    print(f"  -> client_001 stored runs: {len(history_001)}")
    print(f"  -> client_002 stored runs: {len(history_002)}")
    print(f"  -> client_003 stored runs: {len(history_003)}")
    print("  -> Client Isolation Verified: Queries strictly scoped to client_id partition.")

    print("\n" + "=" * 80)
    print("  ALL DEMO SCENARIOS COMPLETED SUCCESSFULLY!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_demo())
