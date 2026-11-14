from app.pii import contains_unmasked_pii


def _routed_case(client):
    resp = client.post("/ask", json={"question": "How do I raise a grievance about my manager?"})
    assert resp.status_code == 200
    return resp.json()["case_id"]


def test_review_flow_approve(client):
    case_id = _routed_case(client)
    resp = client.post(f"/cases/{case_id}/review",
                       json={"decision": "approved", "reviewer": "hr-reviewer",
                             "note": "Draft is accurate; send as-is."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "hr-reviewer"
    assert body["review_note"] == "Draft is accurate; send as-is."


def test_review_flow_reject(client):
    case_id = _routed_case(client)
    resp = client.post(f"/cases/{case_id}/review",
                       json={"decision": "rejected", "reviewer": "hr-reviewer"})
    assert resp.json()["status"] == "rejected"


def test_double_review_returns_409(client):
    case_id = _routed_case(client)
    client.post(f"/cases/{case_id}/review",
                json={"decision": "approved", "reviewer": "hr-reviewer"})
    resp = client.post(f"/cases/{case_id}/review",
                       json={"decision": "approved", "reviewer": "hr-reviewer"})
    assert resp.status_code == 409


def test_unknown_case_returns_404(client):
    resp = client.post("/cases/CASE-9999/review",
                       json={"decision": "approved", "reviewer": "hr-reviewer"})
    assert resp.status_code == 404


def test_cases_list_and_filter(client):
    case_id = _routed_case(client)
    resp = client.get("/cases")
    assert any(c["id"] == case_id for c in resp.json()["cases"])
    resp = client.get("/cases", params={"status": "approved"})
    assert all(c["status"] == "approved" for c in resp.json()["cases"])


def test_audit_log_has_no_unmasked_pii(client, tmp_path):
    client.post("/ask", json={
        "question": "How many days of annual leave do I get? My email is jane@example.com",
        "employee_id": "EMP-001"})
    # Read the actual audit log file the fixture wrote (tmp_path is shared
    # with the client fixture) and assert it contains no unmasked PII.
    audit_text = (tmp_path / "audit.log").read_text(encoding="utf-8")
    assert "jane@example.com" not in audit_text
    assert not contains_unmasked_pii(audit_text)
    resp = client.post("/ask", json={
        "question": "How do I raise a grievance? Contact me at jane@example.com or 9876543210"})
    body = resp.json()
    assert not contains_unmasked_pii(body.get("draft_reply") or "")
    cases = client.get("/cases").json()["cases"]
    assert cases
    assert not contains_unmasked_pii(cases[0]["question"])
    assert not contains_unmasked_pii(cases[0]["draft_reply"])
    # The audit file must also be clean after the routed (PII-bearing) ask.
    audit_text = (tmp_path / "audit.log").read_text(encoding="utf-8")
    assert "jane@example.com" not in audit_text
    assert "9876543210" not in audit_text
    assert not contains_unmasked_pii(audit_text)


def test_review_note_is_masked(client):
    case_id = _routed_case(client)
    resp = client.post(f"/cases/{case_id}/review",
                       json={"decision": "approved", "reviewer": "hr-reviewer",
                             "note": "Confirmed with jane@example.com, call 9876543210."})
    assert resp.status_code == 200
    assert resp.json()["review_note"] == "Confirmed with [EMAIL], call [PHONE]."
