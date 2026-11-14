# Implementation Plan: N28 — Client Employee Onboarding & HR Policy Copilot

## Overview
Build the invented-demo HR + RAG copilot from `SPEC.md` as vertical slices: each slice leaves a working, tested API (seed → retrieve → answer → route/HITL → checklist → eval → site → Docker/CI). One capability, one spec — no multi-module map needed (SPEC §3.1). Default mode is fully offline: deterministic local answerer + stdlib TF-IDF, no Azure key, no Postgres, no Docker required to run or test. Azure OpenAI and pgvector are env-gated options, never requirements.

## Architecture Decisions
- **Local-first, env-gated cloud:** `LocalAnswerer` + in-memory TF-IDF are the default; Azure/pgvector activate only when their env vars are set (SPEC §3.3, §3.5). Rationale: no real key exists; tests and CI must pass offline.
- **Deterministic routing, not LLM judgement:** sensitive classification is a keyword/phrase rule (SPEC §4.1). Rationale: routing must be 100% reproducible and gateable at 20/20.
- **Stdlib TF-IDF, no sklearn/numpy:** the corpus is 20 small clause-shaped docs; a ~100-line stdlib retriever is enough, and it keeps `requirements.txt` minimal (SPEC §3.5).
- **Deterministic eval, no LLM judge / RAGAS:** exact-match on `doc_id` + route (SPEC §8.2). Rationale: offline, reproducible CI gates.
- **One-file seed data (`data/policies.json`):** 20 docs in one JSON file rather than 20 files. Rationale: ponytail — one file to read, diff, and seed; per-file layout adds nothing at this scale.
- **In-memory case store + JSONL audit log:** no DB required for the core loop; Postgres mirrors the same shapes only when configured (SPEC §6).
- **Minimal MCP:** at most one stdlib-only stdio file with two tools (`search_policies`, `get_checklist`); no vendor SDK (SPEC §14).
- **Landing page is a static `site/` page, taste-skill kind `software`:** live-HTML `app-frame` of a real `/ask` exchange; gate outcome on this machine is honestly reported as `ERROR`/`OFF` (no Chrome), never faked (SPEC §10).
- **UI re-planned 2026-11-14 per user direction:** the site is a first-class part of the build — three views in **one app** (Ask workspace, Guided journey, HR dashboard), sharing one fetch wrapper, one answer/citation renderer, one case-card component and one checklist renderer, all live against the API. Not three apps, not landing-page-only.

## Dependency Graph
```
ingest (seed JSON, PII masking)
    │
    ├── retrieval (TF-IDF default; pgvector optional)
    │       │
    │       ├── llm (LocalAnswerer default; Azure gated)
    │       │       │
    │       │       └── agents (LangGraph: supervisor → retrieval/routing/onboarding, HITL)
    │       │               │
    │       │               └── api (FastAPI endpoints, cases, metrics, audit)
    │       │                       │
    │       │                       └── eval (golden set, gates)
    │       │
    │       └── seed script (loads ingest + retrieval)
    │
    └── site (independent — parallelisable once copy is written)
            │
            └── docker + CI (last; CI verifies Docker, this machine cannot)
```

## Task List

### Phase 1: Foundation — ingest, PII, retrieval, seed data
Vertical slice: *seed docs load, mask, and retrieve — no API yet.*
- [ ] Task 1: Scaffold repo — structure, requirements, configs, README disclaimer, `.env.example`, `.gitignore`
- [ ] Task 2: Seed data — `data/policies.json` (20 docs) + `data/golden_eval.json` (20 questions)
- [ ] Task 3: PII masking (`app/pii.py`) + ingest/chunking (`app/ingest.py`)
- [ ] Task 4: TF-IDF retriever (`app/retrieval.py`, stdlib only) + pgvector stub (guarded import)

### Checkpoint: Foundation
- [ ] `python scripts/seed.py` prints 20 docs loaded; `pytest -q` green (PII + retrieval tests)
- [ ] No Azure key, Postgres, or Docker needed so far; review with human before proceeding

### Phase 2: Core — LLM client, graph, API
Vertical slice: *ask a question, get a cited answer or a routed case.*
- [ ] Task 5: LLM client (`app/llm.py`) — `LocalAnswerer` + env-gated Azure client
- [ ] Task 6: LangGraph agents (`app/graph.py`) — supervisor, retrieval, routing, onboarding, HITL gate
- [ ] Task 7: Cases + audit + metrics (`app/cases.py`, `app/metrics.py`)
- [ ] Task 8: FastAPI endpoints (`app/main.py`, `app/models.py`, `app/config.py`) — `/ask`, `/onboarding`, `/cases`, `/metrics`, `/health`

### Checkpoint: Core
- [ ] `uvicorn app.main:app` serves; manual `/ask` (answered + each sensitive class) + checklist + review flow verified with `curl`
- [ ] `pytest -q` green; review with human before proceeding

### Phase 3: Eval + hardening
Vertical slice: *prove it with the golden set and the CI gates.*
- [ ] Task 9: Eval script (`scripts/eval.py`) + `test_eval.py` enforcing SPEC §8.3 gates
- [ ] Task 10: Minimal MCP stdio server (`scripts/mcp_server.py`, 2 tools, stdlib only) — cut if it exceeds one file

### Checkpoint: Eval
- [ ] `python scripts/eval.py` passes all gates; `eval/last_run.json` written; `/metrics` shows measured numbers
- [ ] Thresholds unmet? Tune once per SPEC §8.3 (spec + eval together, reported) — do not silently lower

### Phase 4: Ship surface — site, Docker, CI
Vertical slice: *a stranger can read it, run it, and trust the disclaimer.*
- [ ] Task 11: Static landing page + three-view app (`site/index.html`, `site/assets/app.js`, taste-skill, kind `software`) + copy-lint; run gate, report literal `GATE:` line
- [ ] Task 12: Dockerfile + docker-compose + `schema.sql` + GitHub Actions CI with eval gates

### Checkpoint: Complete
- [ ] All SPEC §1.4 + §16 success criteria met
- [ ] `pytest -q` green offline; eval gates green; README + site carry the invented-demo disclaimer; no secrets committed
- [ ] Human review, then ship (new repo under `ProNoob-Dev`, per SPEC §15.3)

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| TF-IDF misses paraphrased golden questions → recall@3 < 0.85 | Med — gate fails | Seed `keywords` per clause (§6) bridge vocabulary; tune the one `RETRIEVAL_FLOOR` constant once, with the spec updated |
| Routing keyword list misses a golden sensitive phrasing → routing ≠ 1.00 | Med — gate fails | Golden questions written to the §4.1 list; add the exact missing phrase to the list (spec + code together) |
| LangGraph API version drift (`StateGraph` signatures) | Med — build stalls | Pin `langgraph` after first successful install; read installed version's docs, don't guess from training |
| Taste gate cannot run (no Chrome) → reported as ERROR/OFF | Low — expected, honest | Report the literal `GATE:` line; run `copy-lint` (no browser) clean instead; never fake a pass |
| Docker cannot be verified locally (no Docker) | Low — expected | CI builds the image; local report says "not verified locally" explicitly |
| Azure mode untestable without a key | Low — by design | Azure path covered only by a stub-transport test; default local mode is the tested path |

## Parallelisation
- Safe to parallelise after Phase 1: Task 11 (site — needs only the spec + copy) vs Tasks 5–10 (API/eval).
- Must be sequential: Tasks 1→2→3→4 (foundation chain); 5→6→8 (LLM → graph → API); 9 after 8; 12 after 8–9 (CI runs pytest + eval).
- Needs coordination: Tasks 2 and 9 share the golden set — freeze `data/golden_eval.json` in Task 2; Task 9 scores it, it does not rewrite it.

## Open Questions
- SPEC §15: eval thresholds (keep as written unless the human says otherwise); repo name/location confirmation at ship time.
