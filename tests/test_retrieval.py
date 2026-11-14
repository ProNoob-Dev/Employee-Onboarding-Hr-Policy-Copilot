from pathlib import Path

from app.ingest import all_clauses, load_policies


def test_known_query_ranks_expected_doc_top3(copilot):
    top3 = copilot.retriever.retrieve("How many days of annual leave do I get?", k=3)
    assert any(s.clause.doc_id == "LEAVE" for s in top3)


def test_health_insurance_query(copilot):
    top3 = copilot.retriever.retrieve("What does health insurance cover for my family?", k=3)
    assert any(s.clause.doc_id == "BEN-HEALTH" for s in top3)


def test_empty_query_returns_nothing(copilot):
    assert copilot.retriever.retrieve("", k=3) == []


def test_scores_are_cosine_in_range(copilot):
    for scored in copilot.retriever.retrieve("annual leave days", k=3):
        assert 0.0 < scored.score <= 1.0


def test_seed_has_twenty_docs():
    docs = load_policies()
    assert len(docs) == 20
    assert all(3 <= len(d.clauses) <= 6 for d in docs)
    assert len(all_clauses(docs)) >= 60


def test_no_sklearn_or_numpy_in_requirements():
    reqs = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    assert "sklearn" not in reqs and "numpy" not in reqs
