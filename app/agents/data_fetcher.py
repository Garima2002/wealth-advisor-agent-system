"""DataFetcherAgent: Ingests, normalizes, validates client data and retrieves CRM context."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dateutil.parser import parse as parse_date

from app.agents.base import BaseAgent
from app.memory.session_memory import SessionContext
from app.models.client import (
    ClientFinancialProfile,
    CRMClientData,
    PortfolioHolding,
    RawTransaction,
    Transaction,
    TransactionType,
)
from app.tools.interfaces import CRMToolInterface, ToolError


class DataFetcherAgent(BaseAgent):
    """Agent responsible for ingesting, validating, and normalizing client data and CRM context."""

    def __init__(self, crm_tool: CRMToolInterface):
        super().__init__(
            name="DataFetcherAgent",
            role_description="Validates and normalizes client financial data and retrieves CRM profile."
        )
        self.crm_tool = crm_tool

    async def run(
        self,
        client_id: str,
        raw_payload: Optional[Dict[str, Any]],
        context: SessionContext,
        simulate_crm_failure: bool = False,
        simulate_crm_timeout: bool = False,
    ) -> ClientFinancialProfile:
        """Execute the complete data fetching, validation, and normalization pipeline."""
        return await self.execute_stage(
            "ingest_and_normalize",
            context,
            self._process_pipeline,
            client_id,
            raw_payload,
            context,
            simulate_crm_failure,
            simulate_crm_timeout,
        )

    async def _process_pipeline(
        self,
        client_id: str,
        raw_payload: Optional[Dict[str, Any]],
        context: SessionContext,
        simulate_crm_failure: bool,
        simulate_crm_timeout: bool,
    ) -> ClientFinancialProfile:
        payload = raw_payload or {}

        # 1. Fetch CRM Context via abstract tool with graceful degradation
        crm_data: Optional[CRMClientData] = None
        try:
            crm_data = await self.crm_tool.get_client_profile(
                client_id=client_id,
                simulate_failure=simulate_crm_failure,
                simulate_timeout=simulate_crm_timeout,
            )
            context.crm_status = "CONNECTED"
        except ToolError as te:
            context.crm_status = "FAILED"
            context.mark_partial(f"CRM context unavailable: {te}")
            context.add_warning(f"CRM context retrieval failed ({te}). Continuing with transaction-level analysis.")
        except Exception as e:
            context.crm_status = "FAILED"
            context.mark_partial(f"Unexpected CRM failure: {e}")
            context.add_warning(f"Unexpected error retrieving CRM context: {e}")

        # 2. Ingest and Normalize Transactions
        raw_txs = payload.get("transactions", [])
        normalized_txs, data_warnings = self._normalize_transactions(raw_txs)

        for w in data_warnings:
            context.add_warning(w)

        # 3. Ingest Portfolio Holdings if present
        raw_portfolio = payload.get("portfolio", [])
        normalized_portfolio = self._normalize_portfolio(raw_portfolio, data_warnings)

        # 4. Construct Consolidated ClientFinancialProfile
        profile = ClientFinancialProfile(
            client_id=client_id,
            currency=payload.get("currency", "USD").upper(),
            transactions=normalized_txs,
            portfolio=normalized_portfolio if normalized_portfolio else None,
            crm_context=crm_data,
            data_quality_warnings=data_warnings,
            raw_unprocessed_records=len(raw_txs) - len(normalized_txs),
        )

        context.normalized_profile = profile
        return profile

    def _normalize_transactions(self, raw_txs: List[Any]) -> tuple[List[Transaction], List[str]]:
        """Normalize dates, amounts, types, and detect malformed records."""
        normalized: List[Transaction] = []
        warnings: List[str] = []
        now = datetime.now(timezone.utc)

        for idx, item in enumerate(raw_txs):
            if not isinstance(item, dict):
                warnings.append(f"Record #{idx} skipped: Expected JSON object, got {type(item).__name__}")
                continue

            tx_id = str(item.get("id") or f"tx_{uuid.uuid4().hex[:8]}")
            raw_amount = item.get("amount")
            raw_date = item.get("date")
            raw_type = item.get("type")
            category = str(item.get("category") or "uncategorized").strip().lower()
            merchant = item.get("merchant") or item.get("vendor")
            description = item.get("description") or ""

            # Validate Amount
            if raw_amount is None:
                warnings.append(f"Transaction {tx_id}: Missing amount. Record omitted.")
                continue

            try:
                numeric_amount = float(raw_amount)
            except (ValueError, TypeError):
                warnings.append(f"Transaction {tx_id}: Malformed amount '{raw_amount}'. Record omitted.")
                continue

            # Classify Transaction Type and Amount Sign
            tx_type = TransactionType.EXPENSE
            if raw_type:
                type_str = str(raw_type).strip().lower()
                if type_str in ["income", "credit", "deposit", "salary"]:
                    tx_type = TransactionType.INCOME
                elif type_str in ["expense", "debit", "withdrawal", "outflow", "purchase"]:
                    tx_type = TransactionType.EXPENSE
                elif type_str in ["transfer"]:
                    tx_type = TransactionType.TRANSFER
                elif type_str in ["investment"]:
                    tx_type = TransactionType.INVESTMENT
                else:
                    warnings.append(f"Transaction {tx_id}: Unrecognized type '{raw_type}'. Defaulting to expense.")

            # Normalization of negative amounts
            if numeric_amount < 0:
                warnings.append(
                    f"Transaction {tx_id}: Negative amount '{numeric_amount}' normalized to positive magnitude."
                )
                numeric_amount = abs(numeric_amount)

            # Validate Date
            if not raw_date:
                warnings.append(f"Transaction {tx_id}: Missing date. Record omitted.")
                continue

            try:
                parsed_dt = parse_date(str(raw_date))
                formatted_date = parsed_dt.strftime("%Y-%m-%d")

                # Detect future dates
                if parsed_dt.replace(tzinfo=timezone.utc if parsed_dt.tzinfo is None else parsed_dt.tzinfo) > now:
                    warnings.append(f"Transaction {tx_id}: Contains future date '{formatted_date}'.")
            except Exception:
                warnings.append(f"Transaction {tx_id}: Invalid date format '{raw_date}'. Record omitted.")
                continue

            normalized.append(
                Transaction(
                    id=tx_id,
                    date=formatted_date,
                    amount=numeric_amount,
                    type=tx_type,
                    category=category,
                    merchant=str(merchant) if merchant else None,
                    description=str(description) if description else None,
                    currency=str(item.get("currency", "USD")).upper(),
                )
            )

        return normalized, warnings

    def _normalize_portfolio(self, raw_portfolio: List[Any], warnings: List[str]) -> Optional[List[PortfolioHolding]]:
        """Normalize investment portfolio holdings if provided."""
        if not raw_portfolio:
            return None

        holdings: List[PortfolioHolding] = []
        for idx, item in enumerate(raw_portfolio):
            if not isinstance(item, dict):
                warnings.append(f"Portfolio entry #{idx} is not a valid object. Skipped.")
                continue

            name = item.get("asset_name") or item.get("name") or f"Asset_{idx+1}"
            asset_class = str(item.get("asset_class") or "OTHER").upper()
            val = item.get("current_value") or item.get("value")

            try:
                num_val = float(val) if val is not None else 0.0
                if num_val < 0:
                    warnings.append(f"Portfolio holding '{name}' has negative value; set to 0.0.")
                    num_val = 0.0
                holdings.append(
                    PortfolioHolding(
                        asset_name=name,
                        asset_class=asset_class,
                        current_value=num_val,
                        allocation_pct=item.get("allocation_pct")
                    )
                )
            except (ValueError, TypeError):
                warnings.append(f"Portfolio holding '{name}' has malformed value '{val}'. Skipped.")

        return holdings if holdings else None
