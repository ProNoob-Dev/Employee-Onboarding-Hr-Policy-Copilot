"""Measured counters feeding GET /metrics. No invented figures here."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Metrics:
    questions_total: int = 0
    answered: int = 0
    routed_to_hr: int = 0
    answered_with_citation: int = 0
    confidence_sum: float = 0.0
    eval_last_run: dict | None = field(default=None)

    def record_answered(self, confidence: float, cited: bool) -> None:
        self.questions_total += 1
        self.answered += 1
        self.confidence_sum += confidence
        if cited:
            self.answered_with_citation += 1

    def record_routed(self) -> None:
        self.questions_total += 1
        self.routed_to_hr += 1

    def to_dict(self, llm_provider: str, retrieval: str, cases_pending: int,
                cases_approved: int, cases_rejected: int) -> dict:
        total = self.questions_total or 1
        return {
            "llm_provider": llm_provider,
            "retrieval": retrieval,
            "questions_total": self.questions_total,
            "answered": self.answered,
            "routed_to_hr": self.routed_to_hr,
            "autonomous_rate": round(self.answered / total, 3) if self.questions_total else 0.0,
            "citation_coverage": round(
                self.answered_with_citation / self.answered, 3) if self.answered else 0.0,
            "avg_confidence": round(self.confidence_sum / self.answered, 3) if self.answered else 0.0,
            "cases_pending": cases_pending,
            "cases_approved": cases_approved,
            "cases_rejected": cases_rejected,
            "eval_last_run": self.eval_last_run,
        }
