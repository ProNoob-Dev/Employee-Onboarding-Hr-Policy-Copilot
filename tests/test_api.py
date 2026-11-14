def test_health(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "llm_provider": "local", "retrieval": "tfidf"}


def test_ask_validation_422(client):
    assert client.post("/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422
    # Whitespace-only questions strip to empty and are rejected.
    assert client.post("/ask", json={"question": "   "}).status_code == 422


def test_cases_limit_validation_422(client):
    assert client.get("/cases", params={"limit": -1}).status_code == 422
    assert client.get("/cases", params={"limit": 0}).status_code == 422
    assert client.get("/cases", params={"limit": 101}).status_code == 422
    assert client.get("/cases", params={"limit": 100}).status_code == 200


def test_checklist_start_date_format_422(client):
    resp = client.post("/onboarding/EMP-001/checklist",
                       json={"role": "Engineer", "location": "Pune",
                             "start_date": "23 Nov 2026"})
    assert resp.status_code == 422
    resp = client.post("/onboarding/EMP-001/checklist",
                       json={"role": "Engineer", "location": "Pune",
                             "start_date": "2026-11-23"})
    assert resp.status_code == 200


def test_checklist_validation_422(client):
    resp = client.post("/onboarding/EMP-001/checklist", json={"role": "", "location": "Pune"})
    assert resp.status_code == 422


def test_review_validation_422(client):
    resp = client.post("/ask", json={"question": "When will my bonus be paid?"})
    case_id = resp.json()["case_id"]
    bad = client.post(f"/cases/{case_id}/review",
                      json={"decision": "maybe", "reviewer": "hr"})
    assert bad.status_code == 422


def test_cases_unknown_status_422(client):
    assert client.get("/cases", params={"status": "nope"}).status_code == 422


def test_metrics_counts_measured_questions(client):
    client.post("/ask", json={"question": "How many days of annual leave do I get?"})
    client.post("/ask", json={"question": "When will my bonus be paid?"})
    body = client.get("/metrics").json()
    assert body["questions_total"] == 2
    assert body["answered"] == 1
    assert body["routed_to_hr"] == 1
    assert body["autonomous_rate"] == 0.5
    assert body["citation_coverage"] == 1.0
    assert body["cases_pending"] == 1
    assert "88%" not in str(body) and "40%" not in str(body)


def test_root_serves_landing_or_service_json(client):
    resp = client.get("/")
    assert resp.status_code == 200
    # The landing page must actually be served, not just a 200 with no content.
    assert "HR Policy Copilot" in resp.text
    assert "invented demo" in resp.text.lower()


def test_ask_returns_502_when_answerer_fails(tmp_path):
    # API-level: a failing answerer makes /ask fail loudly (502), never a
    # silent fallback to a degraded answer.
    from fastapi.testclient import TestClient

    from app.graph import Copilot
    from app.llm import AzureError
    from app.main import create_app

    class FailingAnswerer:
        def answer(self, question, clauses):
            raise AzureError("Azure OpenAI call failed: ConnectionError")

    app = create_app(Copilot(audit_path=tmp_path / "audit.log",
                             answerer=FailingAnswerer()))
    with TestClient(app) as failing_client:
        resp = failing_client.post(
            "/ask", json={"question": "How many days of annual leave do I get?"})
        assert resp.status_code == 502
