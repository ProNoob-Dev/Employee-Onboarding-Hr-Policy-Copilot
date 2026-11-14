"""In-memory case store and JSONL audit log."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .pii import mask_pii

STATUSES = ("pending_review", "approved", "rejected")


@dataclass
class Case:
    id: str
    question: str
    route_reason: str
    draft_reply: str
    citations: list[dict]
    status: str = "pending_review"
    created_at: str = ""
    reviewed_by: str | None = None
    review_note: str | None = None
    reviewed_at: str | None = None


class CaseStore:
    def __init__(self) -> None:
        self._cases: dict[str, Case] = {}
        self._counter = 0

    def create(self, question: str, route_reason: str, draft_reply: str,
               citations: list[dict]) -> Case:
        self._counter += 1
        case = Case(
            id=f"CASE-{self._counter:04d}",
            question=mask_pii(question),
            route_reason=route_reason,
            draft_reply=mask_pii(draft_reply),
            citations=citations,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._cases[case.id] = case
        return case

    def get(self, case_id: str) -> Case | None:
        return self._cases.get(case_id)

    def list(self, status: str | None = None, limit: int = 20) -> list[Case]:
        cases = list(self._cases.values())
        if status:
            cases = [c for c in cases if c.status == status]
        return cases[:limit]

    def review(self, case_id: str, decision: str, reviewer: str,
               note: str | None) -> Case | None:
        case = self._cases.get(case_id)
        if case is None or case.status != "pending_review":
            return None
        case.status = decision
        case.reviewed_by = reviewer
        case.review_note = mask_pii(note) if note is not None else None
        case.reviewed_at = datetime.now(timezone.utc).isoformat()
        return case

    def counts(self) -> dict[str, int]:
        return {
            status: sum(1 for c in self._cases.values() if c.status == status)
            for status in STATUSES
        }


@dataclass
class AuditLog:
    """JSONL audit events. File writes are best-effort; events are also kept
    in memory so tests can inspect them without touching disk."""

    path: Path | None = None
    events: list[dict] = field(default_factory=list)

    def append(self, event: str, request_id: str, payload: dict) -> None:
        record = {
            "event_id": str(uuid.uuid4()),
            "event": event,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {k: (mask_pii(v) if isinstance(v, str) else v)
                        for k, v in payload.items()},
        }
        self.events.append(record)
        if self.path is not None:
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
            except OSError:
                pass  # audit file failure must never break the request
