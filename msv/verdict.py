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
    RunSummary,
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


def verify_records(
    repo_root: str, records: list[Record]
) -> tuple[list[RecordVerdict], RunSummary]:
    """Verify a batch in input order; return verdicts and aggregate counts.

    len(verdicts) == len(records); the summary buckets sum to len(records).
    """
    verdicts = [verify_record(repo_root, record) for record in records]
    summary = RunSummary(
        current=sum(1 for v in verdicts if v.verdict == "current"),
        stale=sum(1 for v in verdicts if v.verdict == "stale"),
        unverifiable=sum(1 for v in verdicts if v.verdict == "unverifiable"),
    )
    return verdicts, summary


def _classify(results: tuple[AnchorResult, ...]) -> Verdict:
    if not results:
        return "unverifiable"
    if any(_anchor_makes_unverifiable(r) for r in results):
        return "unverifiable"
    if any(not r.found for r in results):
        return "stale"
    return "current"
