# Spec: N28 — Client Employee Onboarding & HR Policy Copilot (HR + RAG)

> **Status:** Spec — approved for planning. No application code has been written against this spec yet.
> **Sources:** Build prompt `~/workspace/your_files/ai-engineer-projects-build-prompts.md` §N28 (lines 1567–1625); explainer `~/workspace/resume_projects_new_invented_2026-11-05.md` §N28 (~line 501). Lifecycle: `spec-driven-development` + `planning-and-task-breakdown` (`~/workspace/vendor/agent-skills/skills/`); `ponytail` (full) for scope discipline.
> **Author / commits:** Jaikishan Bagul <pronoob.dev@gmail.com>, author name `ProNoob-Dev`.

## 0. What this is — read first

**An invented demo / reference project. It is NOT real client work, has no real client, no real employees, and no real HR policy data.** All policy documents, employee names, questions, and answers are synthetic, written for this demo. The README must state this plainly on its first screen, and the landing page must say the same. Never present this project — in the README, the site, a resume line, or an interview answer — as work done for a real client.

The invented project's claimed outcomes in the explainer — **88% of HR queries answered autonomously, first-response 40% faster, manual HR effort down 25%** — are **claims from the invention, not verified results**. This spec **forbids** presenting them as measured results anywhere in the repo. The eval (see §8) must **report measured numbers** (autonomous-answer rate, citation coverage, retrieval recall, routing accuracy, latency) on the golden set, and CI gates use **measured thresholds the deterministic local fallback can actually pass** (§8.3). "40% faster" and "25% less effort" have no baseline in this repo and are therefore **not gated and not claimed** — they are reported as "no baseline; not measured".

## 1. Objective

### 1.1 Problem
New joiners and employees ask HR the same questions all day — leave, benefits, expenses, onboarding paperwork — and answers differ depending on who is asked. HR spends its week on repeat queries instead of the cases that actually need a human.

### 1.2 What we build
One FastAPI + LangGraph copilot that:

1. Answers an HR question **grounded in a cited policy clause** — nothing is answered from memory alone; every non-routed answer carries ≥ 1 citation to a seeded policy document.
2. Builds a **personalised first-week checklist** for a new joiner from their role and location.
3. **Routes only sensitive cases to HR** (pay, grievance, visa) with a draft reply already written, behind a **human-in-the-loop (HITL) gate** — a routed case is never auto-answered.
4. Keeps an **audit trail** of every answer, routing decision, and review.

**UI note (2026-11-14, user direction):** the site is a first-class part of the build, not a landing page alone — three views in **one app** (Ask workspace, Guided journey, HR dashboard), sharing one fetch wrapper, one answer/citation renderer, one case-card component and one checklist renderer, all live against the API in §5. Not three separate apps.

### 1.3 Users
| User | Uses | Does not do |
|---|---|---|
| Employee / new joiner (demo persona) | `POST /ask`, `POST /onboarding/{id}/checklist` | Never sees another employee's PII; never reviews cases |
| HR reviewer (demo persona) | `GET /cases`, `POST /cases/{id}/review` | Does not edit policy docs via the API (seed data only) |
| Maintainer / evaluator | `GET /metrics`, seed script, eval script, CI | Does not need Azure, Postgres, or Docker to run tests |

### 1.4 Success criteria (testable)
- [ ] `POST /ask` on a non-sensitive golden question returns an answer with ≥ 1 citation whose `doc_id` is in the seeded corpus, plus a confidence score in [0, 1].
- [ ] `POST /ask` on a sensitive (pay / grievance / visa) question creates a case in `pending_review` and returns **no substantive answer** — only a routing acknowledgement + case id.
- [ ] `POST /onboarding/{employee_id}/checklist` returns a role- and location-specific first-week checklist (≥ 5 items, each with a due day 1–5 and an owner).
- [ ] `POST /cases/{id}/review` (approve / reject + reviewer note) moves a case to `approved` / `rejected`; a reviewed case cannot be reviewed again (409).
- [ ] `GET /cases` lists the review queue; `GET /metrics` reports measured counts (see §5.6).
- [ ] **All tests pass offline** with no Azure key, no Postgres, no Docker, no network: `pytest` green on a clean checkout after `pip install -r requirements.txt`.
- [ ] CI eval gates (§8.3) pass on the golden set using only the local fallback.
- [ ] No secret is committed; no `.env` file exists in the repo; `README.md` carries the invented-demo disclaimer.
- [ ] Seed script produces exactly 20 policy docs and a 22-question golden eval set; re-running it is idempotent.

## 2. Assumptions (stated up front — correct before building if wrong)

1. **No real Azure OpenAI key exists.** The app must run fully offline. Azure OpenAI is an *optional* provider, used only when `AZURE_OPENAI_API_KEY` is set (see §3.3). Default behaviour is the deterministic local fallback.
2. **No Postgres is guaranteed at test/dev time.** pgvector is an *optional* backend. Default is an in-memory TF-IDF retriever (stdlib only) over the seeded docs, so tests pass with no database.
3. **No Chrome/Chromium and no Docker on this machine** (verified environment fact). The taste-skill finish gate needs headless Chrome, so it **may report `GATE: ERROR` / `GATE: OFF`** for the landing page — that outcome must be reported honestly, never gamed, waived silently, or faked as a pass (see §10).
4. Python is **3.12.3** (verified on this machine). `pip install` works (internet available).
5. Synthetic data only: no real employee names, emails, salaries, or policy text. Seed employee ids are `EMP-001…` style placeholders.
6. Single-tenant demo: no auth, no multi-tenancy, no user accounts. Any "HR reviewer" is a demo persona identified only by a `reviewer` string in the review request body.
7. The 20 policy docs cover the golden questions; the corpus is small on purpose (20 docs, not the explainer's "100+"). The spec does **not** claim 100+ documents.

## 3. Architecture

### 3.1 Capability map (spec-driven-development Phase 0 — one capability, one spec)
This is a single capability (one copilot, one API, one corpus), so no multi-module map is needed. Internal modules and their dependency direction:

| Module id | Responsibility | Depends on |
|---|---|---|
| `ingest` | Seed docs, chunking, PII masking at ingestion | — |
| `retrieval` | TF-IDF (default) / pgvector (optional) retrieval over seeded docs | `ingest` |
| `llm` | Env-configured LLM client + deterministic local fallback answerer | `retrieval` |
| `agents` | LangGraph: supervisor → retrieval / routing / onboarding agents, HITL gate | `retrieval`, `llm` |
| `api` | FastAPI endpoints, request/response models, audit log, metrics | `agents` |
| `eval` | Golden-set runner + deterministic scorer + CI gates | `api`, `retrieval` |
| `site` | Static landing page (`site/`) | — (independent) |

Build order: `ingest` → `retrieval` → `llm` → `agents` → `api` → `eval` → `site` (+ Docker/CI last, alongside `api`).

### 3.2 Agent graph (LangGraph `StateGraph`)
One graph, four agents. State: `{question, employee_id, role, location, retrieved_clauses, route, draft_reply, answer, citations, confidence, case_id, audit_events}`.

```
                ┌─────────────┐
  /ask ───────▶ │ supervisor  │ ── sensitive? ──▶ routing agent ──▶ HITL gate ──▶ case (pending_review)
                └──────┬──────┘        │                              (no answer returned)
                       │ non-sensitive │
                       ▼               │
                retrieval agent        │
                       │               │
                       ▼               │
                (answer + citations,   │
                 confidence)           │
                                       │
  /onboarding ────────────────────────▶ onboarding agent ──▶ checklist
```

- **Supervisor agent:** first node for `/ask`. Classifies the question as `sensitive` or `answerable`. Sensitive = pay / compensation, grievance / complaint / harassment / disciplinary, visa / immigration / work-permit. Classification is a **deterministic keyword + phrase rule** (listed in §4.1), not an LLM judgement — routing must be reproducible offline and 100% correct on the golden set. The LLM (when configured) never overrides a sensitive classification.
- **Retrieval agent:** retrieves top-k (k = 3) clauses from the corpus for the question; returns `doc_id`, `clause_id`, `title`, and the quoted clause text. Nothing is answered from memory alone: if top-1 similarity is below the floor (§4.2), the answer is "I don't know from the policy documents — routed to HR" and a case is created (low-confidence route, distinct `route_reason`).
- **Routing agent:** for sensitive / low-confidence questions, writes a **draft reply** (template-based in local mode; LLM-polished only when Azure is configured) and creates a case. It never sends anything to a real person — there is no email/Slack integration.
- **Onboarding agent:** builds the checklist from the joiner's role + location against seeded onboarding policy docs (paperwork, IT setup, buddy, compliance training). Deterministic template assembly in local mode; no LLM required.
- **HITL gate:** a case in `pending_review` blocks any answer to that question. Only `POST /cases/{id}/review` with `decision: approved | rejected` clears it. Review is recorded in the audit trail with reviewer + note + timestamp. There is no auto-approve path and no timeout that auto-approves.
- **Audit trail:** every graph run appends JSONL events (`audit.log`, local file; in-memory list when running under tests) — `question_received`, `routed` / `answered`, `case_created`, `case_reviewed` — each with request id, timestamps, retrieved `doc_id`s, route, and confidence. Audit events never contain unmasked PII (§7).

### 3.3 LLM client — env-configured, offline by default (HARD CONSTRAINT)
```python
# Decision: one tiny client interface, two implementations. No LangChain.
# - AzureOpenAIClient: used ONLY when AZURE_OPENAI_API_KEY is set (plus
#   AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT; see §9).
# - LocalAnswerer: deterministic template answerer over retrieved clauses.
#   Used when the key is unset — which is the default, and the only mode
#   tests and CI ever exercise.
```
- Local answerer output is fully deterministic: same question + same corpus ⇒ same answer text. It composes the answer **only from retrieved clause text** (extractive template: "According to <title> (<doc_id>, clause <clause_id>): <quoted clause>. …"), plus a confidence derived from retrieval similarity (§4.2). It never invents policy content.
- Azure path: the Azure client sends the question + retrieved clauses only (never raw PII; PII is masked at ingestion and again at request time, §7). If the Azure call fails at runtime, the request **fails loudly (502) — it does not silently fall back** to the local answerer mid-request, so a deploy can never silently downgrade answer quality. (Startup-time selection is the only fallback: key unset ⇒ local mode from the start, reported in `/metrics` as `llm_provider: "local"`.)
- **No real Azure calls in tests, ever.** Tests set no Azure env vars; a test that needs the Azure path uses a stub transport, not the network.

### 3.4 Data flow
```
seed docs (synthetic .md/.json) ──▶ ingest: chunk → PII-mask → index
        │                                  │
        │                          TF-IDF in-memory (default)
        │                          pgvector via Postgres (optional, env-gated)
        ▼
POST /ask ──▶ supervisor ──▶ retrieval ──▶ answer + citations
                      └────▶ routing ──▶ case ──▶ HITL review ──▶ /cases
POST /onboarding ──▶ onboarding agent ──▶ checklist (from policy docs)
Every step ──▶ audit.log (JSONL) + in-memory counters ──▶ GET /metrics
```

### 3.5 Retrieval — pgvector optional, TF-IDF default (HARD CONSTRAINT)
- **Default (no Postgres):** in-memory TF-IDF retriever implemented with the **standard library only** (`re`, `math`, `collections`) — no scikit-learn, no numpy. Tokenise on word boundaries, lowercase, drop a small built-in stopword list; score = cosine over TF-IDF vectors; return top-3. `shortcut: TF-IDF is lexical, not semantic — paraphrases with no shared words will miss; upgrade to embeddings (pgvector + Azure embeddings) only when a real key and Postgres exist.`
- **Optional Postgres backend:** enabled only when `DATABASE_URL` is set. Same interface (`retrieve(query, k) -> list[Clause]`), backed by pgvector (`vector` column, cosine distance). The seed script loads docs into Postgres when `DATABASE_URL` is set, otherwise into the in-memory index. **Tests never require Postgres**; pgvector tests are skipped when `DATABASE_URL` is unset.
- Chunking: one chunk per policy clause (each seed doc is a small list of clauses, each with a stable `clause_id` like `LEAVE-01`). No sliding-window chunker — the corpus is small and clause-shaped by construction.

## 4. Detailed behaviour

### 4.1 Sensitive routing rules (deterministic, listed in full)
A question is `sensitive` if it matches any of these (case-insensitive, word-boundary):
- **Pay:** `pay`, `salary`, `compensation`, `bonus`, `raise`, `payroll`, `payslip`, `deduction`, `overtime pay`.
- **Grievance:** `grievance`, `complaint`, `harassment`, `harass*` (prefix — matches `harassed` / `harassing` / `harassment`), `discrimination`, `bully`, `bullied`, `bullying`, `disciplinary`, `wrongful`, `appeal against`. (Inflected variants `bullied` / `bullying` / `harass*` added 2026-11-14 per review fix; SPEC §13 record.)
- **Visa / immigration:** `visa`, `work permit`, `immigration`, `sponsorship`, `relocation visa`.
- **Low-confidence route (not "sensitive", but also no answer):** top-1 TF-IDF cosine < **0.10** ⇒ `route_reason: "low_confidence"`, case created, acknowledgement returned. Threshold is a constant in one place (`app/config.py`, `RETRIEVAL_FLOOR = 0.10`); the eval (§8) measures how often it fires on the golden set and the threshold may be tuned once, with the tuned value recorded in the eval report — not silently.
- Everything else is `answerable`. The golden set (§8.1) contains at least 3 questions per sensitive class so routing is verified, not assumed.

### 4.2 Confidence
`confidence = round(top1_cosine, 3)` clamped to [0, 1] in local mode (TF-IDF cosine is already in [0, 1]). In Azure mode, confidence is the same retrieval-derived value — the LLM does not invent a confidence. An answer is returned only when `confidence >= 0.10` (same floor as §4.1); otherwise the question is routed.

### 4.3 Checklist rules
Input: `employee_id`, `role` (free text, e.g. "Software Engineer"), `location` (e.g. "Pune" / "Bengaluru" / "Remote — India"). Output: 5–8 items for days 1–5, each `{day, title, detail, owner}` where owner ∈ {`HR`, `IT`, `Manager`, `Buddy`, `Employee`}. Role tailors the IT/equipment + first-project items; location tailors the office-access / local-compliance items; `Remote` replaces office-access items with remote-setup items. Unknown role/location ⇒ generic items, never an error. Checklist items cite the onboarding policy doc (`ONB-*`) they come from.

## 5. Endpoints

Base: FastAPI app `app/main.py`, `GET /health` returns `{"status": "ok", "llm_provider": "local"|"azure", "retrieval": "tfidf"|"pgvector"}`. All JSON. Errors: `422` validation (FastAPI default), `404` unknown case/employee, `409` case already reviewed, `502` Azure call failed (see §3.3). No auth.

### 5.1 `POST /ask`
Request:
```json
{ "question": "How many days of annual leave do I get?", "employee_id": "EMP-001" }
```
(`employee_id` optional; `question` required, 3–500 chars.)
Response — answered:
```json
{
  "request_id": "req_01J...",
  "route": "answered",
  "answer": "According to Leave Policy (LEAVE, clause LEAVE-01): ...",
  "citations": [ { "doc_id": "LEAVE", "clause_id": "LEAVE-01", "title": "Leave Policy", "quote": "..." } ],
  "confidence": 0.87,
  "case_id": null
}
```
Response — routed (sensitive or low-confidence), HTTP 200 (routing is a normal outcome, not an error):
```json
{
  "request_id": "req_01J...",
  "route": "routed_to_hr",
  "route_reason": "sensitive_pay | sensitive_grievance | sensitive_visa | low_confidence",
  "answer": null,
  "citations": [],
  "confidence": 0.0,
  "case_id": "CASE-0007",
  "message": "This question has been routed to HR with a draft reply. An HR reviewer will respond."
}
```

### 5.2 `POST /onboarding/{employee_id}/checklist`
Request: `{ "role": "Software Engineer", "location": "Pune", "start_date": "2026-11-23" }` (`start_date` optional, `YYYY-MM-DD`).
Response:
```json
{
  "employee_id": "EMP-001", "role": "Software Engineer", "location": "Pune",
  "checklist": [
    { "day": 1, "title": "Complete HR paperwork", "detail": "...", "owner": "HR",
      "source": { "doc_id": "ONB", "clause_id": "ONB-01" } }
  ]
}
```

### 5.3 `POST /cases/{id}/review` (HITL)
Request: `{ "decision": "approved | rejected", "reviewer": "hr-reviewer", "note": "Draft is accurate; send as-is." }` (`note` optional).
Response: the updated case (see §5.4). `409` if the case is not `pending_review`.

### 5.4 `GET /cases`
Query params: `?status=pending_review|approved|rejected` (optional), `?limit=20` (default 20, max 100). Response:
```json
{ "cases": [ {
  "id": "CASE-0007", "status": "pending_review",
  "question": "How do I raise a grievance about ...?",
  "route_reason": "sensitive_grievance",
  "draft_reply": "Dear ... (template draft citing GRIEV-02) ...",
  "citations": [ { "doc_id": "GRIEV", "clause_id": "GRIEV-02", "title": "Grievance Policy", "quote": "..." } ],
  "created_at": "2026-11-14T10:00:00Z", "reviewed_by": null, "review_note": null
} ] }
```

### 5.5 `GET /metrics`
```json
{
  "llm_provider": "local", "retrieval": "tfidf",
  "questions_total": 42, "answered": 30, "routed_to_hr": 12,
  "autonomous_rate": 0.714,
  "citation_coverage": 0.967,
  "avg_confidence": 0.81,
  "cases_pending": 5, "cases_approved": 6, "cases_rejected": 1,
  "eval_last_run": { "date": "2026-11-14", "retrieval_recall_at_3": 0.9, "citation_coverage": 1.0, "routing_accuracy": 1.0 } | null
}
```
Definitions: `autonomous_rate = answered / questions_total`; `citation_coverage = answered-with-≥1-citation / answered` (must be 1.0 by construction — the endpoint never returns a citation-less answer); `eval_last_run` is written by the eval script to `eval/last_run.json` and read by `/metrics` if present, else `null`. These are **measured** numbers; the endpoint never reports the invented 88% / 40% / 25% figures.

### 5.6 `GET /` (landing redirect — optional, one line)
`GET /` serves the static landing page from `site/` when present (see §10); the API itself lives under the endpoints above. If `site/` is absent, `GET /` returns `{"service": "hr-policy-copilot", "docs": "/docs"}`. Do not build a second frontend.

## 6. Data model

In-memory first (dicts / Pydantic models); Postgres tables mirror the same shapes when `DATABASE_URL` is set. No migrations framework — one `schema.sql` executed by the seed script when Postgres is used.

| Entity | Fields |
|---|---|
| `PolicyDoc` | `doc_id` (e.g. `LEAVE`), `title`, `category` (leave \| benefits \| expenses \| onboarding \| remote \| pay \| grievance \| visa \| conduct \| it), `clauses: list[Clause]` |
| `Clause` | `clause_id` (e.g. `LEAVE-01`), `doc_id`, `text` (≤ 500 chars), `keywords: list[str]` (seeded, aids TF-IDF on paraphrases) |
| `Case` | `id` (`CASE-0001…`), `question`, `route_reason`, `draft_reply`, `citations: list[Citation]`, `status` (`pending_review \| approved \| rejected`), `created_at`, `reviewed_by`, `review_note`, `reviewed_at` |
| `AuditEvent` | `event_id`, `request_id`, `event` (name), `timestamp`, `payload` (route, doc_ids, confidence, case_id — **no raw question text containing PII; masked, §7**) |
| `GoldenQuestion` | `id` (`Q01…`), `question`, `expected_doc_id`, `expected_route` (`answered \| sensitive_pay \| sensitive_grievance \| sensitive_visa`), `category` |

Storage: cases + counters live in memory in the API process (a module-level store, reset on restart — acceptable for a demo; state this in the README). Postgres, when configured, stores `policy_docs` (with `embedding vector(1536)` nullable — embeddings are **not** computed locally; the column exists for a future Azure-embeddings upgrade and stays NULL in local mode) and `cases`. The in-memory store is the source of truth for tests.

## 7. PII masking at ingestion (HARD CONSTRAINT)
- Masking runs **at ingestion** (seed script + any doc load) and **again on request text** before it reaches the LLM / audit log / draft reply.
- Patterns (stdlib `re`, one module `app/pii.py`, unit-tested with ≥ 1 test per pattern):
  - Email → `[EMAIL]`; phone (Indian + international, `+91` / 10-digit) → `[PHONE]`; Aadhaar (`\d{4} \d{4} \d{4}`) → `[AADHAAR]`; PAN (`[A-Z]{5}\d{4}[A-Z]`) → `[PAN]`; salary / CTC figures in `₹`/`Rs`/`INR` + number → `[COMPENSATION]`; employee id in free text is kept (it is a demo key, `EMP-\d+`).
- Seed docs contain **no real PII at all** — masking is defence-in-depth, and the eval asserts 0 unmasked PII patterns in seeded + masked outputs (`eval` checks the audit log for `[A-Z0-9._%+-]+@[A-Z0-9.-]+` etc.).
- Guardrail: the local answerer only ever quotes seeded clause text, so it cannot leak PII it was never given.

## 8. Seed data + eval plan

### 8.1 Seed data — `scripts/seed.py`, `data/policies/*.json`, `data/golden_eval.json`
- **20 synthetic HR policy docs**, one JSON file per doc (or one `policies.json` — simpler: one file, see §11), each 3–6 clauses, categories: leave (2 docs), benefits (2), expenses (2), onboarding (2), remote work (2), pay (2), grievance (2), visa (2), conduct (2), IT & equipment (2). Every doc: `doc_id`, `title`, `category`, `clauses[]` with `clause_id`, `text`, `keywords`. All text synthetic, written for the demo, no real company policy copied.
- **22-question golden eval set** (`data/golden_eval.json`): 12 `answered` questions (one per non-sensitive category + extras, each with `expected_doc_id`), 3 `sensitive_pay`, 4 `sensitive_grievance`, 3 `sensitive_visa`. Each question's wording shares vocabulary with its expected doc (so TF-IDF can pass) but is phrased as an employee would ask it — not a copy of the clause text. Two questions (Q21 answered, Q22 grievance) carry PII (an email address, a phone number) so the eval's `pii_leak` gate is exercised, not vacuous — the set grew from 20 to 22 questions on 2026-11-14 per review fix (SPEC §13 record).
- `scripts/seed.py` is idempotent (re-run ⇒ same 20 docs, same index) and prints a count. It loads Postgres when `DATABASE_URL` is set, otherwise builds the in-memory index at app startup from the same JSON.

### 8.2 Eval — `scripts/eval.py` (deterministic, no LLM judge, no RAGAS/DeepEval)
For each golden question, call the app (in-process via `httpx.ASGITransport`, no server, no network) and score:
| Metric | Definition | |
|---|---|---|
| `retrieval_recall_at_3` | expected `doc_id` ∈ top-3 retrieved / 22 | |
| `citation_coverage` | answered questions with ≥ 1 citation whose `doc_id` == expected / answered | |
| `routing_accuracy` | predicted `route_reason` == expected route / 22 | |
| `autonomous_rate` | answered / 22 (reported, not gated high — see §8.3) | |
| `pii_leak` | count of unmasked PII patterns in answers + audit log (must be 0) | |
| `avg_latency_ms` | mean `/ask` latency in-process (reported only) | |
Output: `eval/last_run.json` + a one-line console summary. No LLM-as-judge: the scorer is exact-match on `doc_id` / route, so it is deterministic and offline.

### 8.3 CI eval gates (thresholds the local fallback can actually pass)
These are the **only** gates. The invented 88% / 40% / 25% figures are **not** gates.

| Gate | Threshold | Rationale (why the local fallback passes it) |
|---|---|---|
| `pytest` | 100% pass | Offline, deterministic |
| `retrieval_recall_at_3` | ≥ 0.85 (≥ 17/20) | TF-IDF on a 20-doc corpus whose questions share vocabulary with their docs |
| `citation_coverage` | ≥ 0.90 | Answers quote retrieved clauses by construction |
| `routing_accuracy` | = 1.00 (20/20) | Deterministic keyword rules; golden set written to match them |
| `pii_leak` | = 0 | Masking + synthetic-only data |
| `autonomous_rate` | **reported only, no gate** | 12/22 answered is expected by construction (10 are sensitive by design); gating it at 88% would fail by design |

If a gate fails, CI fails. If a threshold proves unpassable in practice, the build agent **lowers the threshold only by editing this spec's table and the eval script together, and says so in its report** — never by editing the eval script alone.

## 9. Stack + dependencies (minimal — ponytail)
Python **3.12.3**. Pin majors in `requirements.txt`; pin exact versions in the build agent's first commit after a successful local install (record them, don't guess them here).

| Dependency | Why | Notes |
|---|---|---|
| `fastapi` | API | |
| `uvicorn` | Server | `[standard]` not needed; plain `uvicorn` |
| `pydantic` | Request/response models (v2, via FastAPI) | No separate pin needed beyond FastAPI's |
| `httpx` | Azure OpenAI calls + tests (`ASGITransport`) | One lib, two jobs |
| `langgraph` | Supervisor / retrieval / routing / onboarding graph | Only graph lib; **no LangChain** (never claimed as a skill) |
| `pytest`, `pytest-asyncio` | Tests | `asyncio_mode = auto` in `pytest.ini` / `pyproject.toml` |
| `psycopg` (optional, `requirements-optional.txt`) | Postgres/pgvector backend only | Import guarded; app runs without it |

**Deliberately not included:** `scikit-learn` / `numpy` (TF-IDF is stdlib), `langchain`, `ragas` / `deepeval` (eval is deterministic exact-match), `langfuse` / `opentelemetry` vendor SDKs (observability is local JSONL + `/metrics`; see §11), any MCP vendor SDK (see §11), `alembic` (one `schema.sql`), `redis`, `celery`. If the build agent finds one is genuinely needed, it must add it to this table with a one-line reason and say so in its report.

### Commands
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # offline-capable run; optional: pip install -r requirements-optional.txt
python scripts/seed.py                   # verify 20 docs load (idempotent)
uvicorn app.main:app --reload --port 8000
pytest -q                                # all tests, offline, no Azure/Postgres/Docker
python scripts/eval.py                   # golden eval; writes eval/last_run.json
docker compose up --build                # api + postgres (needs Docker; NOT verifiable on this machine — see §10)
```

### Environment variables (`.env.example` only — never a real `.env`)
| Var | Required? | Default / meaning |
|---|---|---|
| `AZURE_OPENAI_API_KEY` | No | Unset ⇒ local fallback. Set ⇒ Azure mode |
| `AZURE_OPENAI_ENDPOINT` | Only in Azure mode | e.g. `https://<resource>.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | Only in Azure mode | e.g. `gpt-4o` |
| `DATABASE_URL` | No | Unset ⇒ in-memory TF-IDF. Set ⇒ Postgres + pgvector |
| `LOG_LEVEL` | No | `INFO` |
| `AUDIT_LOG_PATH` | No | `audit.log` (local file; tests override to a tmp path) |

## 10. Project structure
```
employee-onboarding-hr-policy-copilot/
├── README.md                  # disclaimer first (§0), setup, env vars, eval instructions
├── SPEC.md                    # this file
├── tasks/plan.md  tasks/todo.md
├── pyproject.toml             # pytest config (asyncio_mode = auto), ruff if trivially available — else skip
├── requirements.txt  requirements-optional.txt  .env.example  .gitignore
├── Dockerfile  docker-compose.yml  schema.sql
├── .github/workflows/ci.yml   # pip install, pytest, eval gates (§8.3); docker build (CI runner has Docker)
├── app/
│   ├── __init__.py  main.py        # FastAPI app, /health, endpoint wiring
│   ├── config.py    # env vars, RETRIEVAL_FLOOR, sensitive keyword rules
│   ├── models.py    # Pydantic models (AskRequest/Response, Checklist, Case, Metrics)
│   ├── pii.py       # masking (stdlib re)
│   ├── ingest.py    # seed-doc loading + chunking (clause = chunk)
│   ├── retrieval.py # Retriever protocol, TF-IDF (stdlib), pgvector (guarded import)
│   ├── llm.py       # LLMClient protocol, LocalAnswerer, AzureOpenAIClient
│   ├── graph.py     # LangGraph StateGraph: supervisor/retrieval/routing/onboarding, HITL
│   ├── cases.py     # in-memory case store + audit-log writer
│   └── metrics.py   # counters + /metrics assembly
├── data/
│   ├── policies.json          # 20 synthetic docs (ONE file — see §11)
│   └── golden_eval.json       # 20 questions
├── scripts/
│   ├── seed.py  eval.py
│   └── mcp_server.py          # minimal MCP-compatible stdio tool server (see §11)
├── tests/
│   ├── test_pii.py  test_retrieval.py  test_routing.py
│   ├── test_api.py  test_checklist.py  test_cases_hitl.py  test_eval.py
│   └── conftest.py            # TestClient/ASGITransport, tmp audit log, no-Azure fixture
├── eval/last_run.json         # generated by scripts/eval.py (gitignored except a sample? No — gitignored; /metrics reads it if present)
├── site/                      # static landing page (taste-skill; see below)
│   └── index.html
└── audit.log                  # gitignored; local runs only
```

### Landing page — `site/` (taste-skill)
- **Kind: software** — page type `software`, `site-kind: software` (`<html data-type="software">`, `<meta name="page-type" content="software">`, `<meta name="site-kind" content="software">`). It is an AI developer-tool demo, so tech rules apply: the page's own UI as live HTML in one `app-frame` (a real `/ask` request/response mock with a cited clause), one shader/effect at most, 60–80 words a screen outside UI mocks, one hero entrance + 1–2 dealt moments, real product UI not a generic dashboard.
- Copy first, plain voice, h1 naming the category and buyer ("HR policy answers with the clause cited, for employees"). **One hard fact on the first screen must be a measured or plainly synthetic fact** (e.g. "20 synthetic policy docs · 20-question golden eval · answers cite their clause") — never the invented 88% / 40% / 25% as results. The invented-demo disclaimer appears on the page (footer + hero-adjacent line).
- Build with the taste-skill kit (`assets/`, `starter.html`, deal commands, `gate.mjs`) per `~/workspace/custom-skills/taste-skill/SKILL.md`.
- **Environment caveat (honest reporting):** this machine has **no Chrome/Chromium**, so `gate.mjs` / `consistency.mjs` / `check.mjs` **cannot run here** and will report `GATE: ERROR` or `GATE: OFF`. The build agent must run the gate, paste its literal `GATE:` line into its report, and finish — **do not rerun, do not fake a pass, do not edit the kit to clear a check, do not waive a FAIL without a reason in `.taste-skill/waivers.json`**. A `GATE: ERROR/OFF` caused by missing Chrome is a true report of the environment, not a failure of the page; the page still ships with `copy-lint` (no browser needed) run and clean. Docker is likewise absent here, so `docker compose up` is **not verifiable locally** — CI builds the image instead (§12).

## 11. Code style
- Python 3.12, type hints on public functions, `from __future__ import annotations` where it helps; stdlib first; small modules (one responsibility each, §3.1 table).
- Naming: `snake_case` functions/modules, `PascalCase` Pydantic models, `UPPER_SNAKE` constants. No abbreviations beyond `doc_id`, `clause_id`.
- One real snippet — the shape every agent node follows (state in, state out, no side effects except the audit writer, which is injected):
```python
def retrieval_node(state: GraphState) -> GraphState:
    clauses = retrieve(state["question"], k=3)   # Retriever protocol; TF-IDF or pgvector
    return {**state, "retrieved_clauses": clauses}
```
- Errors: validate at the boundary (Pydantic), fail loudly inside (no silent `except: pass`), return the 502/409/404 shapes in §5.
- A shortcut with a known limit gets a one-line comment: `shortcut: <limit>, <when to upgrade>` (see §3.5 for the TF-IDF example).

## 12. Testing strategy
- Framework: `pytest` + `pytest-asyncio` (`asyncio_mode = auto`). Tests live in `tests/`, one file per module (§10). No network, no Azure, no Postgres, no Docker in any test; `conftest.py` asserts the Azure env vars are unset and forces a tmp audit-log path.
- Levels: **unit** — PII masking (≥ 1 test per pattern), TF-IDF ranking (known query ⇒ expected doc in top-3), routing rules (each sensitive class + a non-sensitive control), checklist tailoring (role/location variants); **API** — every endpoint happy-path + error-path (404 unknown case, 409 double-review, 422 bad body) via `httpx.ASGITransport`; **eval** — `test_eval.py` runs the scorer on the golden set and asserts the §8.3 gates (this is the test that enforces the gates locally, so CI and local runs agree).
- Coverage: no hard % gate (ponytail: a coverage number nobody reads is not a gate). The gate is: every module in §10 has a test file, and every endpoint + every routing class is exercised.
- Docker/CI: `docker-compose.yml` (`api` + `postgres:16` with `pgvector/pgvector:pg16`) is exercised by **CI only** (this machine has no Docker). CI (`.github/workflows/ci.yml`): checkout → Python 3.12.3 → `pip install -r requirements.txt` → `pytest -q` → `python scripts/eval.py` (gates §8.3, fail the job on breach) → `docker build` (and `docker compose config -q` if the runner supports it). No deploy step, no secrets in CI.

## 13. Boundaries
- **Always:** run `pytest -q` + `python scripts/eval.py` before committing; keep the invented-demo disclaimer in README + site; mask PII at ingestion; keep every answer cited or routed; update this spec first when a decision changes.
- **Ask first:** adding a dependency (update §9 table with a reason); changing an eval-gate threshold (update §8.3 + eval script together); changing the sensitive-keyword list (§4.1); any change to the public endpoint shapes (§5).
- **Never:** commit secrets or a `.env` file; make a real Azure call from a test; present the 88% / 40% / 25% figures as measured results; present this as real client work; auto-approve a case (no timeout, no default-approve); answer a sensitive question with policy text; edit the taste-skill kit files to clear a check; claim the taste gate or Docker build passed when it was not run / could not run.

## 14. What is explicitly NOT built (ponytail — skipped on purpose)
- **RAGAS / DeepEval** — eval is deterministic exact-match (§8.2); an LLM judge would need a key and would make CI non-deterministic.
- **Langfuse / OpenTelemetry vendor calls** — observability is a local JSONL audit log + `/metrics`. No vendor SDK, no API keys, no network egress by default. (A future `OTEL_ENABLED` env-gated exporter is a follow-up, not this build.)
- **LangChain** — LangGraph alone; the graph is small enough to write directly on `StateGraph`.
- **Auth / multi-tenancy / user accounts** — demo personas only (§2.6). Real auth is a different project.
- **Email / Slack / HRIS sending** — the routing agent writes a *draft reply* stored on the case; nothing is sent anywhere.
- **Embeddings / Azure OpenAI embeddings** — retrieval is lexical TF-IDF by default; the pgvector `embedding` column exists but stays NULL in local mode (§6).
- **A second frontend / separate dashboard app** — the only UI is the one `site/` app (landing page + three views: Ask workspace, Guided journey, HR dashboard); HR review happens in the dashboard view against the same API.
- **MCP vendor SDK** — instead, a **minimal MCP-compatible stdio tool server is acceptable and is the cap**: one file, `scripts/mcp_server.py`, stdlib-only JSON-RPC over stdio, exposing exactly two tools — `search_policies(query, k=3)` and `get_checklist(employee_id, role, location)` — reusing `app.retrieval` / the onboarding logic, no new dependency. If it grows past one file or needs a dependency, cut it.
- **Redis / caching / background workers / migrations framework** — in-memory store + one `schema.sql` (§6, §12).
- **A 100+ document corpus** — the seed is 20 docs by design (§8.1); "100+" in the explainer is an invented scale claim, not a build requirement.

## 15. Open questions (for the human — build agent: do not guess, ask or leave as noted)
1. **Eval thresholds (§8.3):** recall@3 ≥ 0.85 / citation ≥ 0.90 / routing = 1.00 — acceptable, or should routing tolerate 19/20? (Default if unanswered: keep as written; they are the gates the build must meet.)
2. **Landing-page palette/hero deal:** the build agent deals these via taste-skill commands at build time; no pre-approval needed unless the user wants a specific palette.
3. **Repo location:** new GitHub repo under `ProNoob-Dev` (name: `employee-onboarding-hr-policy-copilot`)? Assumed yes; the ship step confirms before pushing.

## 16. Success criteria (restated — the build is done when all of §1.4 holds, plus)
- [ ] `README.md` + `site/index.html` both carry the invented-demo disclaimer; no invented metric is presented as a result anywhere.
- [ ] `pytest -q` green offline; `python scripts/eval.py` green against §8.3 gates; CI workflow exists and is syntactically valid.
- [ ] `Dockerfile` + `docker-compose.yml` exist (build verified in CI, not locally — reported honestly, §10/§12).
- [ ] Taste gate run and its literal `GATE:` line reported (expect `ERROR`/`OFF` on this machine — honest, not gamed).
