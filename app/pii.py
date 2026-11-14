"""PII masking at ingestion and at request time (stdlib ``re`` only).

Employee ids (``EMP-123``) are demo keys and are kept as-is.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # Aadhaar: spaced (4-4-4) or unspaced 12 digits. The lookarounds are the
    # same UUID-tail guard the phone pattern uses: a 12-digit run inside a
    # longer alphanumeric token (e.g. a UUID hex tail) is not an Aadhaar.
    (re.compile(r"(?<![0-9A-Za-z])(?:\d{4} \d{4} \d{4}|\d{12})(?![0-9A-Za-z])"),
     "[AADHAAR]"),
    # PAN: 5 letters, 4 digits, 1 letter (case-insensitive: PANs appear
    # lowercased in free text too).
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I), "[PAN]"),
    # Phone: +91 optional, optional spaces/dashes, 10 digits starting 6-9.
    # Optional parentheses around the groups are tolerated, e.g. (98765 43210).
    # Lookarounds stop it matching inside longer tokens (e.g. a UUID tail
    # like d87016788068, which is 12 hex chars and mostly digits).
    (re.compile(r"(?<![0-9A-Za-z])(?:\+91[\s-]?)?\(?[6-9]\d{4}\)?[\s-]?\d{5}\)?(?![0-9A-Za-z])"),
     "[PHONE]"),
    # Compensation figures: Rs / INR / ₹ followed by a number (a digit is
    # required right after the marker — otherwise the "Rs" tail of words
    # like "hours" / "years" followed by a comma was masked as compensation).
    # An optional lakh / LPA / crore suffix is part of the figure.
    (re.compile(r"(?:Rs\.?|INR|₹)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|LPA|crore))?", re.I),
     "[COMPENSATION]"),
]

# Patterns the eval uses to assert zero unmasked PII in outputs.
LEAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<![0-9A-Za-z])(?:\d{4} \d{4} \d{4}|\d{12})(?![0-9A-Za-z])"),
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I),
    re.compile(r"(?<![0-9A-Za-z])(?:\+91[\s-]?)?\(?[6-9]\d{4}\)?[\s-]?\d{5}\)?(?![0-9A-Za-z])"),
    re.compile(r"(?:Rs\.?|INR|₹)\s*\d[\d,]*", re.I),
]


def mask_pii(text: str) -> str:
    """Replace PII in ``text`` with placeholders. Idempotent."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def contains_unmasked_pii(text: str) -> bool:
    return any(p.search(text) for p in LEAK_PATTERNS)
