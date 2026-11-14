"""Seed script: load the 20 synthetic policy docs (idempotent).

Usage: python scripts/seed.py
With DATABASE_URL set, also writes the docs to Postgres (schema.sql).
Otherwise it just builds the in-memory index and prints the count.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import all_clauses, load_policies  # noqa: E402
from app.retrieval import get_retriever  # noqa: E402

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def main() -> int:
    docs = load_policies()
    clauses = all_clauses(docs)
    retriever = get_retriever(clauses)
    print(f"Loaded {len(docs)} policy docs, {len(clauses)} clauses, "
          f"retrieval backend: {type(retriever).__name__}")
    if DATABASE_URL:
        try:
            import psycopg  # noqa: F401
        except ImportError:
            print("DATABASE_URL is set but psycopg is not installed; "
                  "run: pip install -r requirements-optional.txt")
            return 1
        schema = Path(__file__).resolve().parent.parent / "schema.sql"
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(schema.read_text(encoding="utf-8"))
            for doc in docs:
                for clause in doc.clauses:
                    cur.execute(
                        "INSERT INTO policy_docs (doc_id, clause_id, title, category, text, keywords)"
                        " VALUES (%s, %s, %s, %s, %s, %s)"
                        " ON CONFLICT (clause_id) DO NOTHING",
                        (doc.doc_id, clause.clause_id, doc.title, doc.category,
                         clause.text, clause.keywords),
                    )
            conn.commit()
        print(f"Wrote {len(clauses)} clauses to Postgres.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
