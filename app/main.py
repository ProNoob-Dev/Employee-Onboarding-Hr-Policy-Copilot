"""FastAPI app: endpoints, wiring, error shapes (SPEC section 5)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .graph import Copilot
from .llm import AzureError
from .models import (
    AskRequest,
    AskResponse,
    CaseResponse,
    CasesResponse,
    ChecklistRequest,
    ChecklistResponse,
    ReviewRequest,
)

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def _read_eval_last_run() -> dict | None:
    """Read eval/last_run.json fresh on each call (see /metrics)."""
    eval_path = Path(__file__).resolve().parent.parent / "eval" / "last_run.json"
    if eval_path.exists():
        try:
            return json.loads(eval_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def create_app(copilot: Copilot | None = None) -> FastAPI:
    copilot = copilot or Copilot(audit_path=Path(config.AUDIT_LOG_PATH))
    app = FastAPI(title="HR Policy Copilot", version="0.1.0")
    app.state.copilot = copilot

    @app.get("/health")
    def health():
        return {"status": "ok", "llm_provider": config.llm_provider(),
                "retrieval": config.retrieval_backend()}

    @app.get("/")
    def root():
        index = SITE_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"service": "hr-policy-copilot", "docs": "/docs"}

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest):
        try:
            result = copilot.ask(req.question, req.employee_id)
        except AzureError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return result

    @app.post("/onboarding/{employee_id}/checklist", response_model=ChecklistResponse)
    def checklist(employee_id: str, req: ChecklistRequest):
        return copilot.checklist(employee_id, req.role, req.location, req.start_date)

    @app.get("/cases", response_model=CasesResponse)
    def list_cases(status: str | None = None, limit: int = Query(20, ge=1, le=100)):
        if status is not None and status not in ("pending_review", "approved", "rejected"):
            raise HTTPException(status_code=422, detail=f"unknown status: {status}")
        cases = copilot.cases.list(status=status, limit=limit)
        return {"cases": [_case_response(c) for c in cases]}

    @app.post("/cases/{case_id}/review", response_model=CaseResponse)
    def review_case(case_id: str, req: ReviewRequest):
        case = copilot.cases.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"unknown case: {case_id}")
        updated = copilot.review_case(case_id, req.decision, req.reviewer, req.note)
        if updated is None:
            raise HTTPException(status_code=409, detail=f"case {case_id} already reviewed")
        return updated

    @app.get("/metrics")
    def metrics():
        counts = copilot.cases.counts()
        # Re-read the eval's last run on every request, so a new eval run
        # shows up without restarting the server.
        copilot.metrics.eval_last_run = _read_eval_last_run()
        return copilot.metrics.to_dict(
            config.llm_provider(), config.retrieval_backend(),
            counts["pending_review"], counts["approved"], counts["rejected"])

    if SITE_DIR.exists():
        # The landing page is served at /; its relative assets/... links
        # resolve against /, so serve the kit assets there too.
        app.mount("/assets", StaticFiles(directory=SITE_DIR / "assets"), name="assets")
        app.mount("/site", StaticFiles(directory=SITE_DIR), name="site")

    return app


def _case_response(case) -> dict:
    return {
        "id": case.id, "status": case.status, "question": case.question,
        "route_reason": case.route_reason, "draft_reply": case.draft_reply,
        "citations": case.citations, "created_at": case.created_at,
        "reviewed_by": case.reviewed_by, "review_note": case.review_note,
        "reviewed_at": case.reviewed_at,
    }


app = create_app()
