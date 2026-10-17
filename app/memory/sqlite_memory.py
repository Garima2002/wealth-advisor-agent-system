"""SQLite-backed long-term persistence for client historical summaries and human reviews."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.logging_config import get_logger
from app.models.review import ReviewDecision, ReviewRecord
from app.tools.interfaces import StorageInterface

logger = get_logger("memory.sqlite")


class SQLiteMemoryStore(StorageInterface):
    """Client-isolated long-term persistence engine using SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Client analysis historical summaries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    total_income REAL NOT NULL,
                    total_expenses REAL NOT NULL,
                    net_cash_flow REAL NOT NULL,
                    savings_rate_pct REAL,
                    anomaly_count INTEGER NOT NULL,
                    partial_result INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT NOT NULL
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_client ON analysis_summaries(client_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_session ON analysis_summaries(session_id);")

            # Human review decisions audit table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id TEXT NOT NULL UNIQUE,
                    client_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    reviewer_notes TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    override_details_json TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_finding ON reviews(finding_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_client ON reviews(client_id);")
            conn.commit()

    def save_analysis_summary(
        self,
        client_id: str,
        session_id: str,
        summary_data: Dict[str, Any]
    ) -> None:
        """Persist a client analysis summary with client scoping."""
        timestamp = summary_data.get("timestamp") or datetime.now(timezone.utc).isoformat()
        total_income = float(summary_data.get("total_income", 0.0))
        total_expenses = float(summary_data.get("total_expenses", 0.0))
        net_cash_flow = float(summary_data.get("net_cash_flow", 0.0))
        savings_rate = summary_data.get("savings_rate_pct")
        anomaly_count = int(summary_data.get("anomaly_count", 0))
        partial_result = 1 if summary_data.get("partial_result") else 0

        # Safe serialization without sensitive payloads
        safe_summary = {
            "session_id": session_id,
            "timestamp": timestamp,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_cash_flow": net_cash_flow,
            "savings_rate_pct": savings_rate,
            "anomaly_count": anomaly_count,
            "category_breakdown": summary_data.get("category_breakdown", {}),
        }

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO analysis_summaries
                (client_id, session_id, timestamp, total_income, total_expenses, net_cash_flow, savings_rate_pct, anomaly_count, partial_result, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    session_id,
                    timestamp,
                    total_income,
                    total_expenses,
                    net_cash_flow,
                    savings_rate,
                    anomaly_count,
                    partial_result,
                    json.dumps(safe_summary)
                )
            )
            conn.commit()

        # Enforce max records per client
        self._enforce_client_limit(client_id)

    def get_client_history(
        self,
        client_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve historical summaries strictly scoped to client_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, timestamp, total_income, total_expenses, net_cash_flow, anomaly_count, partial_result, summary_json
                FROM analysis_summaries
                WHERE client_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (client_id, limit)
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "total_income": row["total_income"],
                    "total_expenses": row["total_expenses"],
                    "net_cash_flow": row["net_cash_flow"],
                    "anomaly_count": row["anomaly_count"],
                    "partial_result": bool(row["partial_result"]),
                    "details": json.loads(row["summary_json"]),
                })
            return results

    def save_review(self, review: ReviewRecord) -> None:
        """Insert or update a human review decision."""
        override_json = json.dumps(review.override_details) if review.override_details else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reviews (finding_id, client_id, decision, reviewer_id, reviewer_notes, timestamp, override_details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    decision=excluded.decision,
                    reviewer_id=excluded.reviewer_id,
                    reviewer_notes=excluded.reviewer_notes,
                    timestamp=excluded.timestamp,
                    override_details_json=excluded.override_details_json
                """,
                (
                    review.finding_id,
                    review.client_id,
                    review.decision.value,
                    review.reviewer_id,
                    review.reviewer_notes,
                    review.timestamp,
                    override_json,
                )
            )
            conn.commit()

    def get_review_for_finding(self, finding_id: str) -> Optional[ReviewRecord]:
        """Retrieve human review decision for a finding if present."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT finding_id, client_id, decision, reviewer_id, reviewer_notes, timestamp, override_details_json
                FROM reviews
                WHERE finding_id = ?
                """,
                (finding_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            override_details = json.loads(row["override_details_json"]) if row["override_details_json"] else None
            return ReviewRecord(
                finding_id=row["finding_id"],
                client_id=row["client_id"],
                decision=ReviewDecision(row["decision"]),
                reviewer_id=row["reviewer_id"],
                reviewer_notes=row["reviewer_notes"],
                timestamp=row["timestamp"],
                override_details=override_details,
            )

    def get_reviews_for_client(self, client_id: str) -> List[ReviewRecord]:
        """Retrieve all reviews belonging to a specific client."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT finding_id, client_id, decision, reviewer_id, reviewer_notes, timestamp, override_details_json
                FROM reviews
                WHERE client_id = ?
                ORDER BY timestamp DESC
                """,
                (client_id,)
            )
            rows = cursor.fetchall()
            reviews = []
            for row in rows:
                override_details = json.loads(row["override_details_json"]) if row["override_details_json"] else None
                reviews.append(
                    ReviewRecord(
                        finding_id=row["finding_id"],
                        client_id=row["client_id"],
                        decision=ReviewDecision(row["decision"]),
                        reviewer_id=row["reviewer_id"],
                        reviewer_notes=row["reviewer_notes"],
                        timestamp=row["timestamp"],
                        override_details=override_details,
                    )
                )
            return reviews

    def prune_old_records(self, retention_days: int = settings.RETENTION_DAYS) -> int:
        """Prune analysis summaries older than retention_days."""
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM analysis_summaries WHERE timestamp < ?",
                (cutoff_date,)
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Pruned {deleted} records older than {retention_days} days")
            return deleted

    def _enforce_client_limit(self, client_id: str, max_records: int = settings.MAX_HISTORICAL_RECORDS_PER_CLIENT) -> None:
        """Trim client historical summaries if they exceed max_records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM analysis_summaries
                WHERE client_id = ?
                AND id NOT IN (
                    SELECT id FROM analysis_summaries
                    WHERE client_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                """,
                (client_id, client_id, max_records)
            )
            conn.commit()
