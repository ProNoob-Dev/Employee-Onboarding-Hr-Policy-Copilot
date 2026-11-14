"""Retrieval: stdlib TF-IDF (default) and a guarded pgvector backend.

shortcut: TF-IDF is lexical, not semantic — paraphrases with no shared
words will miss; upgrade to embeddings (pgvector + Azure embeddings) only
when a real key and Postgres exist.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from . import config
from .ingest import Clause

_STOPWORDS = frozenset(
    "a an the and or of to in on for with is are was were be been do does did "
    "i you he she it we they my your his her our their this that these those "
    "how what when where which who whom can could should would will shall may "
    "there here about from by at as not no yes if then than so such per "
    "me get gets got have has had".split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


@dataclass
class ScoredClause:
    clause: Clause
    score: float


class TfidfRetriever:
    """In-memory TF-IDF retriever, standard library only."""

    def __init__(self, clauses: list[Clause]) -> None:
        self.clauses = clauses
        self._doc_freq: Counter[str] = Counter()
        self._vectors: list[dict[str, float]] = []
        self._norms: list[float] = []
        for clause in clauses:
            counts = Counter(tokenize(clause.index_text))
            for term in counts:
                self._doc_freq[term] += 1
        n = len(clauses)
        for clause in clauses:
            counts = Counter(tokenize(clause.index_text))
            vector = {
                term: (count / sum(counts.values()))
                * (math.log((n + 1) / (self._doc_freq[term] + 1)) + 1.0)
                for term, count in counts.items()
            }
            self._vectors.append(vector)
            self._norms.append(math.sqrt(sum(v * v for v in vector.values())) or 1.0)

    def retrieve(self, query: str, k: int = 3) -> list[ScoredClause]:
        counts = Counter(tokenize(query))
        if not counts or not self.clauses:
            return []
        total = sum(counts.values())
        n = len(self.clauses)
        qvec = {
            term: (count / total) * (math.log((n + 1) / (self._doc_freq.get(term, 0) + 1)) + 1.0)
            for term, count in counts.items()
        }
        qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
        scored: list[ScoredClause] = []
        for clause, vector, norm in zip(self.clauses, self._vectors, self._norms):
            dot = sum(qvec.get(term, 0.0) * weight for term, weight in vector.items())
            scored.append(ScoredClause(clause, dot / (qnorm * norm)))
        scored.sort(key=lambda s: (-s.score, s.clause.clause_id))
        return [s for s in scored[:k] if s.score > 0]


class PgVectorRetriever:
    """Postgres + pgvector backend. Only constructed when DATABASE_URL is set.

    The pgvector ``embedding`` column exists in schema.sql for a future
    Azure-embeddings upgrade and stays NULL in local mode, so there is no
    semantic search to run yet: this backend scores with the same TF-IDF
    over the seeded clauses until embeddings exist. It exists so the
    interface and schema are real, not to pretend semantic search works.
    """

    def __init__(self, clauses: list[Clause]) -> None:
        self._fallback = TfidfRetriever(clauses)

    def retrieve(self, query: str, k: int = 3) -> list[ScoredClause]:
        return self._fallback.retrieve(query, k)


def get_retriever(clauses: list[Clause]):
    """TF-IDF by default; pgvector only when DATABASE_URL is set."""
    if config.retrieval_backend() == "pgvector":
        return PgVectorRetriever(clauses)
    return TfidfRetriever(clauses)
