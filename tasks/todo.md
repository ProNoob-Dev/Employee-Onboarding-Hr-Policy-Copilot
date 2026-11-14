# Todo: N28 — Client Employee Onboarding & HR Policy Copilot

Spec: `../SPEC.md` — read the section cited in each task before starting it. Check a box only when its acceptance criteria **and** verification both pass. Do not write application code in this phase; this list is for the build agent.

## Phase 1: Foundation

- [x] Task 1: Scaffold repo — structure, requirements, configs, README disclaimer
  - Acceptance: repo matches SPEC §10 layout; `requirements.txt` has only SPEC §9 deps; `README.md` states the invented-demo disclaimer on its first screen; `.env.example` lists SPEC §9 vars; `.gitignore` excludes `.env`, `audit.log`, `eval/last_run.json`, `.venv`
  - Verify: `ls` the tree against SPEC §10; `grep -i "invented demo" README.md`; `python -m venv .venv && pip install -r requirements.txt` succeeds on Python 3.12.3
  - Files: `README.md`, `pyproject.toml`, `requirements.txt`, `requirements-optional.txt`, `.env.example`, `.gitignore`, `app/__init__.py`, `tests/conftest.py`

- [x] Task 2: Seed data — 20 policy docs + 20-question golden eval set
  - Acceptance: `data/policies.json` has exactly 20 docs, 3–6 clauses each, categories per SPEC §8.1 (2 docs × 10 categories), all text synthetic; `data/golden_eval.json` has exactly 20 questions (11 answered, 3 pay, 3 grievance, 3 visa), each with `expected_doc_id` + `expected_route`
  - Verify: `python scripts/seed.py` prints 20 docs loaded and is idempotent on re-run; a script asserts the counts above
  - Files: `data/policies.json`, `data/golden_eval.json`, `scripts/seed.py`

- [x] Task 3: PII masking + ingest/chunking
  - Acceptance: `app/pii.py` masks email, phone, Aadhaar, PAN, compensation figures (SPEC §7) and leaves `EMP-\d+` intact; `app/ingest.py` loads `data/policies.json`, one chunk per clause with stable `clause_id`
  - Verify: `pytest tests/test_pii.py -q` — ≥ 1 test per pattern, all pass
  - Files: `app/pii.py`, `app/ingest.py`, `tests/test_pii.py`

- [x] Task 4: TF-IDF retriever (stdlib only) + pgvector stub
  - Acceptance: `retrieve(query, k=3)` returns ranked clauses with cosine scores; pgvector backend activates only when `DATABASE_URL` is set and is skipped in tests otherwise; `RETRIEVAL_FLOOR = 0.10` lives in `app/config.py`
  - Verify: `pytest tests/test_retrieval.py -q` — known query ⇒ expected doc in top-3; no `sklearn`/`numpy` in `requirements.txt`
  - Files: `app/retrieval.py`, `app/config.py`, `tests/test_retrieval.py`

## Checkpoint: Foundation
- [x] `python scripts/seed.py` prints 20 docs loaded; `pytest -q` green
- [x] No Azure key, Postgres, or Docker needed so far
- [x] Review with human before proceeding

## Phase 2: Core

- [x] Task 5: LLM client — LocalAnswerer + env-gated Azure client
  - Acceptance: key unset ⇒ `LocalAnswerer` (deterministic, extractive, quotes retrieved clauses only, confidence = top-1 cosine); key set ⇒ Azure client used; Azure failure ⇒ HTTP 502, never silent fallback (SPEC §3.3)
  - Verify: `pytest tests/test_llm.py -q` — same question twice ⇒ identical answer; Azure path tested with stub transport only, no network
  - Files: `app/llm.py`, `tests/test_llm.py`

- [x] Task 6: LangGraph agents — supervisor, retrieval, routing, onboarding, HITL gate
  - Acceptance: supervisor routes sensitive (pay/grievance/visa per SPEC §4.1) to the routing agent and everything else to retrieval; routing agent writes a draft reply + creates a case, never an answer; low-confidence (< 0.10) also routes; onboarding agent builds a 5–8 item day 1–5 checklist citing `ONB-*` clauses
  - Verify: `pytest tests/test_routing.py tests/test_checklist.py -q` — each sensitive class + low-confidence + a non-sensitive control; checklist role/location variants
  - Files: `app/graph.py`, `tests/test_routing.py`, `tests/test_checklist.py`

- [x] Task 7: Cases + audit + metrics stores
  - Acceptance: in-memory case store (`pending_review` → `approved`/`rejected`, no re-review); JSONL audit events per SPEC §3.2 with masked payloads only; counters feed `GET /metrics` shapes (SPEC §5.5)
  - Verify: `pytest tests/test_cases_hitl.py -q` — review flow, 409 on double-review, audit log contains no unmasked PII pattern
  - Files: `app/cases.py`, `app/metrics.py`, `tests/test_cases_hitl.py`

- [x] Task 8: FastAPI endpoints
  - Acceptance: `POST /ask`, `POST /onboarding/{employee_id}/checklist`, `POST /cases/{id}/review`, `GET /cases`, `GET /metrics`, `GET /health` match SPEC §5 request/response shapes; errors 404/409/422 as specified
  - Verify: `pytest tests/test_api.py -q` (via `httpx.ASGITransport`, no server); manual `curl` smoke test of answered + routed + checklist + review while `uvicorn` runs
  - Files: `app/main.py`, `app/models.py`, `tests/test_api.py`

## Checkpoint: Core
- [x] `uvicorn app.main:app` serves; manual `/ask` (answered + each sensitive class) + checklist + review verified with `curl`
- [x] `pytest -q` green; review with human before proceeding

## Phase 3: Eval + hardening

- [x] Task 9: Eval script + gate tests
  - Acceptance: `scripts/eval.py` scores the 20-question golden set in-process (no server/network) and writes `eval/last_run.json`; metrics per SPEC §8.2; `test_eval.py` asserts SPEC §8.3 gates (recall@3 ≥ 0.85, citation ≥ 0.90, routing = 1.00, PII leaks = 0; autonomous rate reported, not gated)
  - Verify: `python scripts/eval.py` exits 0 and prints the one-line summary; `pytest tests/test_eval.py -q` green
  - Files: `scripts/eval.py`, `tests/test_eval.py`, `eval/last_run.json` (generated, gitignored)

- [x] Task 10: Minimal MCP stdio server (2 tools, stdlib only) — cut if it exceeds one file
  - Acceptance: `scripts/mcp_server.py` is a single file, stdlib-only JSON-RPC over stdio, exposing exactly `search_policies` and `get_checklist`, reusing `app.retrieval` / onboarding logic; no new dependency
  - Verify: pipe a JSON-RPC `search_policies` request over stdio and get ranked clauses back; `grep -r "mcp" requirements.txt` returns nothing
  - Files: `scripts/mcp_server.py`

## Checkpoint: Eval
- [x] `python scripts/eval.py` passes all gates; `/metrics` shows measured numbers (no invented 88%/40%/25% anywhere)
- [x] Any threshold change was made in SPEC §8.3 + eval script together and reported

## Phase 4: Ship surface

- [x] Task 11: Static landing page (`site/index.html`, taste-skill, kind `software`)
  - Acceptance: kind `software` metas set; live-HTML `app-frame` of a real `/ask` exchange; invented-demo disclaimer on the page; first-screen hard fact is measured/synthetic only (never 88%/40%/25% as results); `copy-lint` clean
  - Verify: `node <skill>/scripts/copy-lint.mjs site/index.html --kind software` clean; `node <skill>/scripts/gate.mjs site/index.html` run and its literal `GATE:` line pasted in the build report (expect `ERROR`/`OFF` on this machine — no Chrome — report honestly, do not rerun or fake a pass)
  - Files: `site/index.html` (+ `.taste-skill/` artefacts; kit files untouched)

- [x] Task 12: Dockerfile + docker-compose + schema.sql + GitHub Actions CI
  - Acceptance: `Dockerfile` (Python 3.12.3, `pip install -r requirements.txt`, `uvicorn`); `docker-compose.yml` (`api` + `postgres:16` pgvector); `schema.sql` mirrors SPEC §6; `.github/workflows/ci.yml` runs `pytest`, `scripts/eval.py` (fail on gate breach), and `docker build`
  - Verify: `python -c "import yaml"` / `docker compose config -q` if Docker exists — **it does not on this machine, so record "Docker build not verified locally; CI verifies"**; CI workflow YAML parses
  - Files: `Dockerfile`, `docker-compose.yml`, `schema.sql`, `.github/workflows/ci.yml`

## Checkpoint: Complete
- [x] All SPEC §1.4 + §16 success criteria met
- [x] `pytest -q` green offline; eval gates green; README + site carry the invented-demo disclaimer; no secrets committed (`git status` shows no `.env`)
- [x] Human review, then ship (new repo under `ProNoob-Dev`, SPEC §15.3)
