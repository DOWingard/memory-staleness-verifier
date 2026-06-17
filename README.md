# memory-staleness-verifier (`msv`)

A store-agnostic Python library and CLI that re-checks whether code-anchored
agent-memory entries are still current against a live Python repository. Each
record's anchors (a file path plus an optional symbol) are resolved by **AST
parse only** — the target repo's code is never imported or executed, so the tool
is safe to run against untrusted repositories.

A long-lived memory can keep serving a crisp, high-confidence fact that has
silently gone stale (a renamed function, a deleted module). This verifier
classifies each record so a consumer can demote or queue correction.

## Verdicts

- `current` — every anchor resolves (file exists and, if given, the symbol).
- `stale` — at least one anchor's file or symbol is missing.
- `unverifiable` — the record has no anchors, an anchor path is outside the repo,
  or a file cannot be parsed.

Precedence: `unverifiable` > `stale` > `current`.

## Library

```python
from msv import verify_records, Record, Anchor

records = [
    Record(id="m1", claim_text="parse takes three args",
           anchors=(Anchor(path="pkg/parser.py", symbol="parse"),)),
]
verdicts, summary = verify_records("/path/to/repo", records)
# verdicts: list[RecordVerdict]; summary: RunSummary(current, stale, unverifiable)
```

`resolve_anchor(repo_root, anchor)` exposes the single-anchor resolver directly.

## CLI

```
msv --records records.json --repo /path/to/repo [--out verdicts.json] \
    [--require-env NAME ...]
```

- `--records` is a JSON file or `-` for stdin.
- `--out` defaults to stdout.
- `--require-env NAME` (repeatable) is checked fail-fast before any work.

Exit codes: `0` no record stale, `1` at least one record stale, `2` usage/input
error (bad JSON, missing repo, missing required env). A target-repo condition
never crashes the tool — it becomes a verdict.

### Input shape

```json
[
  {"id": "m1", "claim_text": "...",
   "anchors": [{"path": "pkg/parser.py", "symbol": "parse"}],
   "recorded_at_commit": "abc123"}
]
```

`symbol` and `recorded_at_commit` are optional; `recorded_at_commit` is echoed as
informational data only and never affects a verdict.

### Output shape

```json
{
  "verdicts": [
    {"id": "m1", "verdict": "current",
     "anchors": [{"path": "pkg/parser.py", "symbol": "parse",
                  "found": true, "location": "pkg/parser.py:1", "reason": "ok"}]}
  ],
  "summary": {"current": 1, "stale": 0, "unverifiable": 0}
}
```

## Requirements

Python 3.11+, standard library only. `pytest` for the test suite.
