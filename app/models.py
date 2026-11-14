"""Pydantic request/response models (SPEC section 5)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    doc_id: str
    clause_id: str
    title: str
    quote: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    employee_id: str | None = None

    @field_validator("question", mode="before")
    @classmethod
    def _strip_question(cls, value):
        # A whitespace-only question strips to "" and then fails min_length.
        return value.strip() if isinstance(value, str) else value


class AskResponse(BaseModel):
    request_id: str
    route: str  # answered | routed_to_hr
    route_reason: str | None = None
    answer: str | None = None
    citations: list[Citation] = []
    confidence: float = 0.0
    case_id: str | None = None
    message: str | None = None


class ChecklistRequest(BaseModel):
    role: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=100)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ChecklistItem(BaseModel):
    day: int
    title: str
    detail: str
    owner: str
    source: Citation | None = None


class ChecklistResponse(BaseModel):
    employee_id: str
    role: str
    location: str
    checklist: list[ChecklistItem]


class ReviewRequest(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")
    reviewer: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class CaseResponse(BaseModel):
    id: str
    status: str
    question: str
    route_reason: str
    draft_reply: str
    citations: list[Citation] = []
    created_at: str
    reviewed_by: str | None = None
    review_note: str | None = None
    reviewed_at: str | None = None


class CasesResponse(BaseModel):
    cases: list[CaseResponse]
