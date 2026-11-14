"""Seed-doc loading and chunking. One chunk per policy clause."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .pii import mask_pii

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Clause:
    clause_id: str
    doc_id: str
    title: str
    category: str
    text: str
    keywords: list[str] = field(default_factory=list)

    @property
    def index_text(self) -> str:
        """Text the retriever indexes: clause text plus seeded keywords."""
        return self.text + " " + " ".join(self.keywords)


@dataclass
class PolicyDoc:
    doc_id: str
    title: str
    category: str
    clauses: list[Clause]


def load_policies(path: Path | str | None = None) -> list[PolicyDoc]:
    """Load and PII-mask the seeded policy docs. Idempotent."""
    path = Path(path) if path else DATA_DIR / "policies.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    docs: list[PolicyDoc] = []
    for doc in raw:
        clauses = [
            Clause(
                clause_id=c["clause_id"],
                doc_id=doc["doc_id"],
                title=doc["title"],
                category=doc["category"],
                text=mask_pii(c["text"]),
                keywords=list(c.get("keywords", [])),
            )
            for c in doc["clauses"]
        ]
        docs.append(PolicyDoc(doc["doc_id"], doc["title"], doc["category"], clauses))
    return docs


def all_clauses(docs: list[PolicyDoc]) -> list[Clause]:
    return [clause for doc in docs for clause in doc.clauses]


def load_golden(path: Path | str | None = None) -> list[dict]:
    path = Path(path) if path else DATA_DIR / "golden_eval.json"
    return json.loads(path.read_text(encoding="utf-8"))
