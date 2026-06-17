"""msv — memory-staleness-verifier public API.

Re-exports are finalized in the CLI chunk; the data contract is available now.
"""
from __future__ import annotations

from msv.types import (
    Anchor,
    AnchorResult,
    Record,
    RecordVerdict,
    RunSummary,
    Verdict,
)

__all__ = [
    "Anchor",
    "AnchorResult",
    "Record",
    "RecordVerdict",
    "RunSummary",
    "Verdict",
]
