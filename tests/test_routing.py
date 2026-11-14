import pytest

from app.config import classify_sensitive

SENSITIVE = [
    ("My salary seems lower than agreed", "sensitive_pay"),
    ("When will my bonus be paid?", "sensitive_pay"),
    ("How do I raise a grievance about my manager?", "sensitive_grievance"),
    ("I want to report harassment by a colleague", "sensitive_grievance"),
    ("I was bullied by my team lead", "sensitive_grievance"),
    ("My manager keeps bullying me", "sensitive_grievance"),
    ("I am being harassed at work", "sensitive_grievance"),
    ("Will the company sponsor my work visa?", "sensitive_visa"),
    ("How do I renew my work permit?", "sensitive_visa"),
]


@pytest.mark.parametrize("question,expected", SENSITIVE)
def test_sensitive_classification(question, expected):
    assert classify_sensitive(question) == expected


def test_non_sensitive_control():
    assert classify_sensitive("How many days of annual leave do I get?") is None


def test_pay_word_boundary():
    # "payment" must not trigger the "pay" rule.
    assert classify_sensitive("How is the expense payment made?") is None


@pytest.mark.parametrize("question,expected", SENSITIVE)
def test_ask_routes_sensitive_to_hr(client, question, expected):
    resp = client.post("/ask", json={"question": question, "employee_id": "EMP-001"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "routed_to_hr"
    assert body["route_reason"] == expected
    assert body["answer"] is None
    assert body["case_id"] is not None


def test_ask_answers_non_sensitive_with_citation(client):
    resp = client.post("/ask", json={"question": "How many days of annual leave do I get each year?"})
    body = resp.json()
    assert body["route"] == "answered"
    assert body["citations"]
    assert body["citations"][0]["doc_id"] == "LEAVE"
    assert 0.0 <= body["confidence"] <= 1.0
    assert "LEAVE-01" in body["answer"]


def test_low_confidence_routes_to_hr(client):
    resp = client.post("/ask", json={"question": "zebra quantum pineapple giraffe"})
    body = resp.json()
    assert body["route"] == "routed_to_hr"
    assert body["route_reason"] == "low_confidence"
    assert body["case_id"] is not None


def test_sensitive_case_carries_citations(client):
    # A routed sensitive case must carry the retrieved clauses as citations,
    # and the draft reply must cite the clause (SPEC section 5.4).
    resp = client.post("/ask", json={"question": "How do I raise a grievance about my manager?"})
    case_id = resp.json()["case_id"]
    cases = client.get("/cases").json()["cases"]
    case = next(c for c in cases if c["id"] == case_id)
    assert case["citations"]
    assert any(c["clause_id"] == "GRIEV-02" for c in case["citations"])
    # The draft cites the top retrieved clause (GRIEV-01 here).
    assert "GRIEV-01" in case["draft_reply"]

