"""Golden-set eval: deterministic exact-match scorer, no LLM judge.

Calls the app in-process via Starlette TestClient (no server, no network).
httpx 0.28's ASGITransport is async-only, so the sync TestClient is the
in-process transport here; the eval still never touches the network.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import load_golden  # noqa: E402
from app.main import create_app  # noqa: E402
from app.pii import contains_unmasked_pii  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

GATES = {
    "retrieval_recall_at_3": 0.85,
    "citation_coverage": 0.90,
    "routing_accuracy": 1.00,
    "pii_leak": 0,
}


def run_eval() -> dict:
    golden = load_golden()
    app = create_app()
    copilot = app.state.copilot
    transport = TestClient(app)
    recall_hits = 0
    answered = 0
    cited_correct = 0
    routing_hits = 0
    pii_leaks = 0
    latencies: list[float] = []

    with transport as client:
        for item in golden:
            question = item["question"]
            top3 = copilot.retriever.retrieve(question, k=3)
            if any(s.clause.doc_id == item["expected_doc_id"] for s in top3):
                recall_hits += 1
            start = time.perf_counter()
            resp = client.post("/ask", json={"question": question, "employee_id": "EMP-001"})
            latencies.append((time.perf_counter() - start) * 1000)
            body = resp.json()
            if contains_unmasked_pii(body.get("answer") or ""):
                pii_leaks += 1
            if body["route"] == "answered":
                answered += 1
                if any(c["doc_id"] == item["expected_doc_id"] for c in body["citations"]):
                    cited_correct += 1
                predicted = "answered"
            else:
                predicted = body.get("route_reason")
            if predicted == item["expected_route"]:
                routing_hits += 1
        for event in copilot.audit.events:
            if contains_unmasked_pii(json.dumps(event)):
                pii_leaks += 1
        # Cases created by the eval run: a routed question's draft reply and
        # stored question must be masked too, not just the /ask answer.
        cases = client.get("/cases", params={"limit": 100}).json()["cases"]
        for case in cases:
            if contains_unmasked_pii(case.get("question") or ""):
                pii_leaks += 1
            if contains_unmasked_pii(case.get("draft_reply") or ""):
                pii_leaks += 1

    total = len(golden)
    result = {
        "date": time.strftime("%Y-%m-%d"),
        "questions": total,
        "retrieval_recall_at_3": round(recall_hits / total, 3),
        "citation_coverage": round(cited_correct / answered, 3) if answered else 0.0,
        "routing_accuracy": round(routing_hits / total, 3),
        "autonomous_rate": round(answered / total, 3),
        "pii_leak": pii_leaks,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
    }
    return result


def main() -> int:
    result = run_eval()
    out = ROOT / "eval" / "last_run.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"eval: recall@3={result['retrieval_recall_at_3']} "
        f"citation={result['citation_coverage']} "
        f"routing={result['routing_accuracy']} "
        f"pii_leaks={result['pii_leak']} "
        f"autonomous_rate={result['autonomous_rate']} "
        f"avg_latency_ms={result['avg_latency_ms']}"
    )
    failures = []
    if result["retrieval_recall_at_3"] < GATES["retrieval_recall_at_3"]:
        failures.append("retrieval_recall_at_3")
    if result["citation_coverage"] < GATES["citation_coverage"]:
        failures.append("citation_coverage")
    if result["routing_accuracy"] < GATES["routing_accuracy"]:
        failures.append("routing_accuracy")
    if result["pii_leak"] != GATES["pii_leak"]:
        failures.append("pii_leak")
    if failures:
        print(f"GATES FAILED: {', '.join(failures)}")
        return 1
    print("GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
