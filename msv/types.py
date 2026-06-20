"""Machine-readable data contract: frozen dataclasses + the Verdict literal.

These types ARE the contract; the JSON wire shape is derived from them at the
serialization seam, never duplicated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# The three verdict strings are also the exact JSON wire values, so they are
# modeled as a Literal rather than an enum (no second name for the same fact).
Verdict = Literal["current", "stale", "unverifiable"]

# Closed set of machine-stable reason codes a consumer may branch on. Kept here
# as the single source so resolution/verdict use identical spellings.
REASON_OK = "ok"
REASON_FILE_MISSING = "file_missing"
REASON_PATH_OUTSIDE_REPO = "path_outside_repo"
REASON_PARSE_ERROR = "parse_error"
REASON_SYMBOL_MISSING = "symbol_missing"
REASON_NO_SYMBOL_REQUESTED = "no_symbol_requested"
REASON_NO_ANCHORS = "no_anchors"
# Anchor points at a file whose language the resolver cannot parse.
REASON_UNSUPPORTED_LANGUAGE = "unsupported_language"


@dataclass(frozen=True, slots=True)
class Anchor:
    path: str  # repo-relative path to a Python file
    symbol: str | None = None  # module-level function/class, or "Class.method"


@dataclass(frozen=True, slots=True)
class Record:
    id: str
    claim_text: str
    anchors: tuple[Anchor, ...] = ()
    recorded_at_commit: str | None = None  # informational only; never acted on


@dataclass(frozen=True, slots=True)
class AnchorResult:
    path: str
    symbol: str | None
    found: bool
    location: str | None  # e.g. "pkg/auth.py:42" when found, else None
    reason: str  # machine-stable code + detail, e.g. "symbol_missing: refresh"


@dataclass(frozen=True, slots=True)
class RecordVerdict:
    id: str
    verdict: Verdict
    anchors: tuple[AnchorResult, ...]


@dataclass(frozen=True, slots=True)
class RunSummary:
    current: int
    stale: int
    unverifiable: int
