-- Schema for the optional Postgres backend (SPEC section 6).
-- Run by scripts/seed.py when DATABASE_URL is set. The embedding column
-- stays NULL in local mode; it exists for a future Azure-embeddings upgrade.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_docs (
    clause_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    embedding vector(1536)
);

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    route_reason TEXT NOT NULL,
    draft_reply TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by TEXT,
    review_note TEXT,
    reviewed_at TIMESTAMPTZ
);
