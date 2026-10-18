"""Integration tests for FastAPI endpoints: /analyze, /health, /sessions, /clients/history, /reviews."""

from fastapi.testclient import TestClient


def test_api_health_endpoint(api_client: TestClient):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["uptime_status"] == "operational"


def test_api_dashboard_endpoint(api_client: TestClient):
    response = api_client.get("/")
    assert response.status_code == 200
    assert "Wealth Advisor" in response.text
    assert "Analysis Control Center" in response.text


def test_api_analyze_normal_workflow(api_client: TestClient, sample_normal_data: dict):
    payload = {
        "client_id": "client_001",
        "client_profile": sample_normal_data,
        "mock_crm_failure": False,
    }
    response = api_client.post(
        "/analyze",
        json=payload,
        headers={"X-Correlation-ID": "test-corr-101"}
    )
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == "test-corr-101"

    data = response.json()
    assert data["client_id"] == "client_001"
    assert data["financial_summary"]["net_cash_flow"] > 0
    assert data["system_status"]["partial_result"] is False
    assert len(data["actionable_insights"]) > 0


def test_api_analyze_crm_failure_partial_result(api_client: TestClient, sample_normal_data: dict):
    payload = {
        "client_id": "client_001",
        "client_profile": sample_normal_data,
        "mock_crm_failure": True,
    }
    response = api_client.post("/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["system_status"]["partial_result"] is True
    assert data["system_status"]["crm_status"] == "FAILED"


def test_api_analyze_validation_error(api_client: TestClient):
    # Missing required 'client_id'
    payload = {"client_profile": {}}
    response = api_client.post("/analyze", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


def test_api_session_and_history_endpoints(api_client: TestClient, sample_normal_data: dict):
    # 1. Run analysis to create a session and persist summary
    analyze_resp = api_client.post(
        "/analyze",
        json={"client_id": "client_session_test", "client_profile": sample_normal_data}
    )
    assert analyze_resp.status_code == 200
    session_id = analyze_resp.json()["metadata"]["session_id"]

    # 2. Query session endpoint
    sess_resp = api_client.get(f"/sessions/{session_id}")
    assert sess_resp.status_code == 200
    sess_data = sess_resp.json()
    assert sess_data["session_id"] == session_id
    assert sess_data["client_id"] == "client_session_test"
    assert len(sess_data["traces"]) > 0

    # 3. Query unknown session -> 404
    unknown_resp = api_client.get("/sessions/sess_non_existent")
    assert unknown_resp.status_code == 404

    # 4. Query client history endpoint
    hist_resp = api_client.get("/clients/client_session_test/history")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["client_id"] == "client_session_test"
    assert hist_data["count"] >= 1
    assert hist_data["records"][0]["session_id"] == session_id


def test_api_submit_review_endpoint(api_client: TestClient):
    finding_id = "finding_api_test_01"
    review_payload = {
        "decision": "APPROVE",
        "reviewer_id": "ADV_BOB",
        "reviewer_notes": "Reviewed with customer and verified legitimate."
    }
    response = api_client.post(
        f"/reviews/{finding_id}?client_id=client_review_test",
        json=review_payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["finding_id"] == finding_id
    assert data["decision"] == "APPROVE"
    assert data["reviewer_id"] == "ADV_BOB"
