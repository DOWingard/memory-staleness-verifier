"""msv — memory-staleness-verifier.

Public API: the importable verification functions, the deep resolver, and the
data contract. The CLI is a second surface, available as the `msv` console
script or via `from msv.cli import main`.
"""
from __future__ import annotations

from msv.resolution import fingerprint_anchor, resolve_anchor
from msv.types import (
    Anchor,
    AnchorResult,
    Record,
    RecordVerdict,
    RunSummary,
    Verdict,
)
from msv.verdict import verify_record, verify_records

__all__ = [
    "Anchor",
    "AnchorResult",
    "Record",
    "RecordVerdict",
    "RunSummary",
    "Verdict",
    "fingerprint_anchor",
    "resolve_anchor",
    "verify_record",
    "verify_records",
]
