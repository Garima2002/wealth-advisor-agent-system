"""Tests for short-term SessionMemoryStore and long-term SQLiteMemoryStore."""

from datetime import datetime, timedelta, timezone
from app.memory.session_memory import SessionMemoryStore
from app.memory.sqlite_memory import SQLiteMemoryStore


def test_session_memory_lifecycle():
    store = SessionMemoryStore(max_active_sessions=2)
    s1 = store.create_session("client_1")
    s2 = store.create_session("client_2")

    assert store.get_session(s1.session_id) is not None
    assert store.get_session(s2.session_id) is not None

    # Exceed capacity: oldest session s1 should be evicted
    s3 = store.create_session("client_3")
    assert store.get_session(s1.session_id) is None
    assert store.get_session(s3.session_id) is not None

    # Deletion
    assert store.remove_session(s2.session_id) is True
    assert store.get_session(s2.session_id) is None


def test_sqlite_memory_persistence_and_client_isolation(test_storage: SQLiteMemoryStore):
    # Save runs for client_A
    test_storage.save_analysis_summary(
        client_id="client_A",
        session_id="sess_A1",
        summary_data={
            "total_income": 5000.0,
            "total_expenses": 2000.0,
            "net_cash_flow": 3000.0,
            "savings_rate_pct": 60.0,
            "anomaly_count": 1,
            "partial_result": False,
        }
    )

    # Save runs for client_B
    test_storage.save_analysis_summary(
        client_id="client_B",
        session_id="sess_B1",
        summary_data={
            "total_income": 8000.0,
            "total_expenses": 3000.0,
            "net_cash_flow": 5000.0,
            "savings_rate_pct": 62.5,
            "anomaly_count": 0,
            "partial_result": False,
        }
    )

    history_a = test_storage.get_client_history("client_A")
    history_b = test_storage.get_client_history("client_B")

    # Strict client isolation: A must see only A, B must see only B
    assert len(history_a) == 1
    assert history_a[0]["session_id"] == "sess_A1"
    assert history_a[0]["total_income"] == 5000.0

    assert len(history_b) == 1
    assert history_b[0]["session_id"] == "sess_B1"
    assert history_b[0]["total_income"] == 8000.0


def test_sqlite_memory_retention_pruning(test_storage: SQLiteMemoryStore):
    # Insert old record (120 days ago)
    old_date = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    test_storage.save_analysis_summary(
        client_id="client_retention",
        session_id="sess_old",
        summary_data={
            "timestamp": old_date,
            "total_income": 1000.0,
            "total_expenses": 500.0,
            "net_cash_flow": 500.0,
            "anomaly_count": 0,
        }
    )

    # Insert fresh record (today)
    test_storage.save_analysis_summary(
        client_id="client_retention",
        session_id="sess_new",
        summary_data={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_income": 2000.0,
            "total_expenses": 1000.0,
            "net_cash_flow": 1000.0,
            "anomaly_count": 0,
        }
    )

    # Prune records older than 90 days
    pruned_count = test_storage.prune_old_records(retention_days=90)
    assert pruned_count == 1

    remaining = test_storage.get_client_history("client_retention")
    assert len(remaining) == 1
    assert remaining[0]["session_id"] == "sess_new"
