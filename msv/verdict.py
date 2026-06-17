"""The single owner of the current/stale/unverifiable classification policy.

Precedence (one source of truth): unverifiable dominates stale dominates
current. A record with no anchors is unverifiable. An anchor whose file/symbol
is missing makes the record stale; an anchor whose path escapes the repo or
whose file will not parse makes the record unverifiable.
"""
from __future__ import annotations

from msv.resolution import resolve_anchor
from msv.types import (
    REASON_PARSE_ERROR,
    REASON_PATH_OUTSIDE_REPO,
    AnchorResult,
    Record,
    RecordVerdict,
    Verdict,
)

# Anchor reason-code prefixes that make the whole record unverifiable.
_UNVERIFIABLE_PREFIXES = (REASON_PATH_OUTSIDE_REPO, REASON_PARSE_ERROR)


def _anchor_makes_unverifiable(result: AnchorResult) -> bool:
    return result.reason.startswith(_UNVERIFIABLE_PREFIXES)


def verify_record(repo_root: str, record: Record) -> RecordVerdict:
    """Resolve every anchor in input order and classify the record."""
    results = tuple(resolve_anchor(repo_root, anchor) for anchor in record.anchors)
    verdict = _classify(results)
    return RecordVerdict(id=record.id, verdict=verdict, anchors=results)


def _classify(results: tuple[AnchorResult, ...]) -> Verdict:
    if not results:
        return "unverifiable"
    if any(_anchor_makes_unverifiable(r) for r in results):
        return "unverifiable"
    if any(not r.found for r in results):
        return "stale"
    return "current"
