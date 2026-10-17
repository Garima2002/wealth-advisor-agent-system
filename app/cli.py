"""Command Line Interface for the Wealth Advisor Multi-Agent System."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.agents.analyzer import AnalyzerAgent
from app.agents.data_fetcher import DataFetcherAgent
from app.agents.insight import InsightAgent
from app.agents.orchestrator import OrchestratorAgent
from app.memory.session_memory import SessionMemoryStore
from app.memory.sqlite_memory import SQLiteMemoryStore
from app.models.api import AnalyzeRequest
from app.models.review import ReviewDecision, ReviewRequest
from app.services.financial_rules import FinancialRulesEngine
from app.services.review_service import HumanReviewService
from app.tools.mock_crm import MockCRMAdapter


def create_orchestrator(db_path: str = "wealth_advisor.db") -> tuple[OrchestratorAgent, HumanReviewService, SQLiteMemoryStore]:
    """Helper to assemble agents and services for CLI execution."""
    storage = SQLiteMemoryStore(db_path=db_path)
    session_store = SessionMemoryStore()
    crm_tool = MockCRMAdapter()
    rules_engine = FinancialRulesEngine()

    data_fetcher = DataFetcherAgent(crm_tool=crm_tool)
    analyzer = AnalyzerAgent(rules_engine=rules_engine)
    insight_agent = InsightAgent()

    orchestrator = OrchestratorAgent(
        data_fetcher=data_fetcher,
        analyzer=analyzer,
        insight_agent=insight_agent,
        session_store=session_store,
        storage=storage,
    )
    review_service = HumanReviewService(storage=storage)
    return orchestrator, review_service, storage


async def run_analysis_cli(file_path: str, client_id: str, mock_fail: bool = False):
    """Executes an analysis workflow from a local JSON file."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    orchestrator, _, _ = create_orchestrator()
    request = AnalyzeRequest(
        client_id=client_id,
        client_profile=payload,
        mock_crm_failure=mock_fail
    )

    print(f"\n>>> Running Wealth Advisor Multi-Agent Analysis for Client: {client_id}")
    print(f">>> Source Payload: {file_path} (CRM Failure Simulation: {mock_fail})\n")

    response = await orchestrator.execute_analysis(request)

    print("=" * 70)
    print("FINANCIAL SUMMARY")
    print("=" * 70)
    s = response.financial_summary
    print(f"Total Income:     ${s.total_income:,.2f}")
    print(f"Total Expenses:   ${s.total_expenses:,.2f}")
    print(f"Net Cash Flow:    ${s.net_cash_flow:,.2f}")
    print(f"Savings Rate:     {s.savings_rate_pct if s.savings_rate_pct is not None else 'N/A'}%")
    print(f"Transactions:     {s.transaction_count} ({s.period_start} to {s.period_end})")
    print(f"Category Spend:   {json.dumps(s.category_breakdown, indent=2)}")

    print("\n" + "=" * 70)
    print(f"ANOMALY FINDINGS ({len(response.anomaly_findings)})")
    print("=" * 70)
    for idx, a in enumerate(response.anomaly_findings, 1):
        print(f"[{idx}] {a.finding_id} | {a.anomaly_type.value} | Severity: {a.severity.value}")
        print(f"    Observed:    {a.observed_value}")
        print(f"    Baseline:    {a.comparison_baseline}")
        print(f"    Explanation: {a.explanation}")
        print(f"    Limitation:  {a.limitations}")
        print(f"    Verify:      {a.recommended_verification}")
        print(f"    Status:      {a.review_status.value}")

    print("\n" + "=" * 70)
    print(f"ACTIONABLE ADVISORY INSIGHTS ({len(response.actionable_insights)})")
    print("=" * 70)
    for idx, ins in enumerate(response.actionable_insights, 1):
        print(f"[{idx}] [{ins.category.value}] {ins.title} (Confidence: {ins.confidence_score})")
        print("    Facts:")
        for fact in ins.observed_facts:
            print(f"      - {fact}")
        print("    Explanations:")
        for exp in ins.possible_explanations:
            print(f"      - {exp}")
        print("    Suggested Next Steps:")
        for step in ins.suggested_next_steps:
            print(f"      - {step}")

    if response.data_quality_warnings:
        print("\n" + "=" * 70)
        print(f"DATA QUALITY & DEGRADATION WARNINGS ({len(response.data_quality_warnings)})")
        print("=" * 70)
        for w in response.data_quality_warnings:
            print(f"  * {w}")

    print("\n" + "=" * 70)
    print(f"EXECUTION METRICS & TRACE (Duration: {response.metadata['duration_ms']}ms)")
    print("=" * 70)
    for t in response.system_status["execution_traces"]:
        print(f"  [{t['agent']}] Stage: {t['stage']:<25} Status: {t['status']:<8} Time: {t['duration_ms']}ms")

    return response


def main():
    parser = argparse.ArgumentParser(description="Wealth Advisor Multi-Agent CLI")
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze client JSON file")
    analyze_parser.add_argument("--file", required=True, help="Path to client JSON file")
    analyze_parser.add_argument("--client-id", default="client_001", help="Target client ID")
    analyze_parser.add_argument("--mock-fail", action="store_true", help="Simulate CRM failure")

    args = parser.parse_args()
    if args.command == "analyze":
        asyncio.run(run_analysis_cli(args.file, args.client_id, args.mock_fail))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
