"""Eval gates (SPEC section 8.3) enforced as a test so CI and local agree."""

import pytest

from scripts.eval import GATES, run_eval


def test_eval_gates_pass(monkeypatch, tmp_path):
    # Isolate the eval run: point the audit log at a tmp file so pytest
    # never appends to the repo's real audit.log. run_eval() itself does
    # not write eval/last_run.json (only scripts/eval.py's main() does).
    monkeypatch.setattr("app.config.AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    result = run_eval()
    assert result["retrieval_recall_at_3"] >= GATES["retrieval_recall_at_3"], result
    assert result["citation_coverage"] >= GATES["citation_coverage"], result
    assert result["routing_accuracy"] >= GATES["routing_accuracy"], result
    assert result["pii_leak"] == GATES["pii_leak"], result
    # Autonomous rate is reported only, never gated: 12/22 answered by design
    # (10 of 22 questions are sensitive, including the PII-bearing ones).
    assert 0.5 <= result["autonomous_rate"] <= 0.6, result


def test_eval_audit_path_is_isolated(monkeypatch, tmp_path):
    # The eval's audit writes must land in the tmp path, not audit.log.
    monkeypatch.setattr("app.config.AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    run_eval()
    assert (tmp_path / "audit.log").exists()
