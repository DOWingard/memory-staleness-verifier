"""The single source of the documented JSON wire shapes.

Every conversion between the dataclass contract and JSON lives here, so the wire
shape is defined once. Input-contract violations (a record missing `id` or
`claim_text`, a non-list `anchors`, an anchor missing `path`) raise ValueError
with a precise message — distinct from a target-repo condition, which becomes a
verdict rather than an error.
"""
from __future__ import annotations

import json

from msv.types import (
    Anchor,
    Record,
    RecordVerdict,
    RunSummary,
)


def record_from_dict(d: dict) -> Record:
    """Build a Record from a plain dict, validating the input contract."""
    if "id" not in d:
        raise ValueError("record is missing required field 'id'")
    if "claim_text" not in d:
        raise ValueError("record is missing required field 'claim_text'")

    raw_anchors = d.get("anchors", [])
    if not isinstance(raw_anchors, list):
        raise ValueError("record field 'anchors' must be a list")

    anchors = tuple(_anchor_from_dict(item) for item in raw_anchors)
    return Record(
        id=d["id"],
        claim_text=d["claim_text"],
        anchors=anchors,
        recorded_at_commit=d.get("recorded_at_commit"),
    )


def _anchor_from_dict(d: dict) -> Anchor:
    if not isinstance(d, dict) or "path" not in d:
        raise ValueError("anchor is missing required field 'path'")
    return Anchor(path=d["path"], symbol=d.get("symbol"))


def records_from_json(text: str) -> list[Record]:
    """Parse a JSON array of record objects into a list of Records."""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("records JSON must be a list of record objects")
    return [record_from_dict(item) for item in data]


def verdict_to_dict(v: RecordVerdict) -> dict:
    """Serialize a RecordVerdict to the documented output object shape."""
    return {
        "id": v.id,
        "verdict": v.verdict,
        "anchors": [
            {
                "path": a.path,
                "symbol": a.symbol,
                "found": a.found,
                "location": a.location,
                "reason": a.reason,
            }
            for a in v.anchors
        ],
    }


def summary_to_dict(s: RunSummary) -> dict:
    return {
        "current": s.current,
        "stale": s.stale,
        "unverifiable": s.unverifiable,
    }


def run_to_json(verdicts: list[RecordVerdict], summary: RunSummary) -> str:
    """Serialize a full run to a deterministic JSON string.

    Determinism follows from fixed key insertion order and stable input order;
    no sorting or clock or RNG is involved.
    """
    payload = {
        "verdicts": [verdict_to_dict(v) for v in verdicts],
        "summary": summary_to_dict(summary),
    }
    return json.dumps(payload, indent=2)
