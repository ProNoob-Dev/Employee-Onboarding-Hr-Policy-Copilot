"""Environment config and routing rules (single source of truth)."""

from __future__ import annotations

import os
import re

RETRIEVAL_FLOOR = 0.10
RETRIEVAL_K = 3

# LOG_LEVEL and AUDIT_LOG_PATH are read once at import time (frozen);
# the Azure vars are read lazily via the functions below, so tests can
# set/unset them with monkeypatch.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
AUDIT_LOG_PATH = os.environ.get("AUDIT_LOG_PATH", "audit.log")


def azure_api_key() -> str:
    return os.environ.get("AZURE_OPENAI_API_KEY", "")


def azure_endpoint() -> str:
    return os.environ.get("AZURE_OPENAI_ENDPOINT", "")


def azure_deployment() -> str:
    return os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")


def llm_provider() -> str:
    return "azure" if azure_api_key() else "local"


def retrieval_backend() -> str:
    return "pgvector" if os.environ.get("DATABASE_URL") else "tfidf"


# Sensitive routing rules (SPEC section 4.1). Word-boundary regexes so
# "payment" does not match "pay" and "visa" does not match "advisable".
# A phrase ending in "*" is a prefix match (e.g. "harass*" matches
# harassed / harassing / harassment); every other phrase matches as a
# whole word. Order matters: grievance and visa are checked before pay,
# because the bare word "raise" (pay) also appears in "raise a grievance".
SENSITIVE_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "sensitive_grievance",
        ("grievance", "complaint", "harassment", "harass*", "discrimination",
         "bully", "bullied", "bullying", "disciplinary", "wrongful",
         "appeal against"),
    ),
    (
        "sensitive_visa",
        ("visa", "work permit", "immigration", "sponsorship", "relocation visa"),
    ),
    (
        "sensitive_pay",
        ("pay", "salary", "compensation", "bonus", "raise", "payroll",
         "payslip", "deduction", "overtime pay"),
    ),
]

def _phrase_regex(phrase: str) -> str:
    if phrase.endswith("*"):
        return re.escape(phrase[:-1]) + r"\w*"
    return re.escape(phrase)


_COMPILED: list[tuple[str, re.Pattern[str]]] = [
    (reason, re.compile(r"\b(?:" + "|".join(_phrase_regex(p) for p in phrases) + r")\b", re.I))
    for reason, phrases in SENSITIVE_RULES
]


def classify_sensitive(question: str) -> str | None:
    """Return the sensitive route reason, or None if the question is answerable."""
    for reason, pattern in _COMPILED:
        if pattern.search(question):
            return reason
    return None
