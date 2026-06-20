# memory-staleness-verifier (`msv`)

A store-agnostic Python library and CLI that re-checks whether code-anchored
agent-memory entries are still current against a live code repository — anchors
into Python, JavaScript, and TypeScript (including JSX/TSX and `.d.ts`).

## What it's for

Agent memories anchored to code rot silently. An entry like "function `parse`
takes three arguments" or "module `auth` owns token refresh" is true when
captured and wrong the moment the code changes. Read-time confidence signals
catch *blended* recalls (a read that mixes several facts) but not *stale* ones:
a crisp, high-confidence recall of an outdated fact passes every read-time check
and actively misleads the agent. After capture, nothing re-validates a stored
fact against the world, so a memory store's trust in a fact rises with reuse
while its correctness silently decays.

`msv` closes that gap. Given a set of memory records and a target repository, it
mechanically classifies each record as `current`, `stale`, or `unverifiable`
with machine-readable evidence, so a consumer can demote or queue correction of
the entries that no longer hold. Each record's anchors (a file path plus an
optional symbol) are resolved by **parsing only** — Python via the standard-
library AST, JavaScript and TypeScript via tree-sitter grammars. The target
repo's code is never imported or executed, so the tool is safe to run against
untrusted repositories.

## Install

Python 3.11+. Runtime dependencies: `tree-sitter` plus the JavaScript and
TypeScript grammar packages, installed automatically. From the project root:

```
pip install -e .
```

This installs the `msv` package and the `msv` console script. To install the
test extra as well:

```
pip install -e ".[dev]"
```

## Quickstart

```python
from msv import verify_records, Record, Anchor

records = [
    Record(
        id="m1",
        claim_text="parse takes three args",
        anchors=(Anchor(path="pkg/parser.py", symbol="parse"),),
    ),
    Record(
        id="m2",
        claim_text="Button is the primary CTA component",
        anchors=(Anchor(path="src/Button.tsx", symbol="Button"),),
    ),
]
verdicts, summary = verify_records("/path/to/repo", records)

for v in verdicts:
    print(v.id, v.verdict)          # e.g. "m1 current"
print(summary.current, summary.stale, summary.unverifiable)
```

## Verdicts

- `current` — every anchor resolves (the file exists and, if a symbol is given,
  the symbol resolves).
- `stale` — at least one anchor's file or symbol is missing.
- `unverifiable` — the record has no anchors, an anchor path is outside the repo,
  a file cannot be parsed, or the file's language is unsupported.

Precedence (one source of truth): `unverifiable` > `stale` > `current`.

## Supported languages

The anchor's file extension selects the parser. A bare `symbol` resolves to a
named, top-level definition; a dotted `Class.method` resolves to a method in
that top-level class body (one level deep).

| Language   | Extensions                         | Resolvable symbols |
|------------|------------------------------------|--------------------|
| Python     | `.py`                              | `def` / `async def` / `class`; `Class.method` |
| JavaScript | `.js` `.jsx` `.mjs` `.cjs`         | function & class declarations, and `const`/`let`/`var` bound to a function or arrow; `Class.method` |
| TypeScript | `.ts` `.tsx` `.mts` `.cts` `.d.ts` | the JavaScript forms, plus `abstract class` and `.d.ts` ambient `declare`d functions/classes |

`export` and `export default` are transparent — `export function f` resolves as
`f`. Type-only and value-only declarations are intentionally **not** resolvable
symbols, so an anchor to one is reported missing: TypeScript `interface`, `type`,
and `enum`, and non-function constants such as `const MAX = 5`. A file whose
extension is not in the table is reported `unsupported_language` (an
`unverifiable` verdict).

For JavaScript/TypeScript a syntax error in one part of a file does not hide
cleanly-parsed declarations elsewhere; a name that cannot be cleanly located in a
file that fails to parse is reported `unverifiable`, never missing, so a syntax
error never reads as a deletion. Resolution is structural, not semantic: it
confirms a declaration with that name still exists, and does not follow
re-exports, path aliases, or barrel files.

## API / Reference

Import the public surface from the top-level package:

```python
from msv import (
    verify_records, verify_record, resolve_anchor,
    Record, Anchor, AnchorResult, RecordVerdict, RunSummary, Verdict,
)
```

### Functions

```python
verify_records(repo_root: str, records: list[Record]) -> tuple[list[RecordVerdict], RunSummary]
```
Verify a batch in input order. `len(verdicts) == len(records)` and the summary
buckets sum to `len(records)`.

```python
verify_record(repo_root: str, record: Record) -> RecordVerdict
```
Resolve every anchor of one record in input order and classify it.

```python
resolve_anchor(repo_root: str, anchor: Anchor) -> AnchorResult
```
The single-anchor resolver. A total function — it never raises on an expected
condition (missing file, parse error, path outside the repo, unsupported
language); each becomes an `AnchorResult`. `found` is `True` iff the anchor path
is inside `repo_root`, the file exists, parses, and (if a symbol is given) the
symbol resolves in that file's language.

### Data types

All data types are frozen dataclasses; `Verdict` is the literal
`"current" | "stale" | "unverifiable"`.

```python
Anchor(path: str, symbol: str | None = None)
```
`path` is repo-relative; its extension selects the language. `symbol` is a
top-level function/class name, or a dotted `"Class.method"` resolved one level
deep into the top-level class body (nested defs are out of scope). See
[Supported languages](#supported-languages) for the per-language symbol forms.

```python
Record(id: str, claim_text: str,
       anchors: tuple[Anchor, ...] = (),
       recorded_at_commit: str | None = None)
```
`recorded_at_commit` is informational only and never affects a verdict.

```python
AnchorResult(path: str, symbol: str | None, found: bool,
             location: str | None, reason: str)
```
`location` is e.g. `"pkg/auth.py:42"` when found, else `None`. `reason` is a
machine-stable code, optionally with detail — one of: `ok`,
`no_symbol_requested`, `file_missing`, `symbol_missing`, `path_outside_repo`,
`parse_error`, `unsupported_language` (the last five carry a `: <detail>`
suffix).

```python
RecordVerdict(id: str, verdict: Verdict, anchors: tuple[AnchorResult, ...])
RunSummary(current: int, stale: int, unverifiable: int)
```

### CLI

```
msv --records records.json --repo /path/to/repo [--out verdicts.json] \
    [--require-env NAME ...]
```

- `--records` (required) is a JSON file path, or `-` to read from stdin.
- `--repo` (required) is the local repository to verify against (its files may be
  Python, JavaScript, or TypeScript).
- `--out` is where the verdicts JSON is written (default: stdout).
- `--require-env NAME` (repeatable) is checked fail-fast before any work.

Exit codes:

- `0` — no record is stale.
- `1` — at least one record is stale.
- `2` — usage / input error (bad JSON, missing or non-directory repo, unreadable
  records, or a missing required env var).

A target-repo condition (missing file, syntax error, path outside the repo)
never crashes the tool — it becomes a verdict, never an exit code.

#### Input shape

A JSON array of record objects:

```json
[
  {"id": "m1", "claim_text": "...",
   "anchors": [{"path": "pkg/parser.py", "symbol": "parse"}],
   "recorded_at_commit": "abc123"}
]
```

`symbol` and `recorded_at_commit` are optional; `recorded_at_commit` is echoed
as informational data only and never affects a verdict. A record missing `id` or
`claim_text`, a non-list `anchors`, or an anchor missing `path` is an input-
contract violation (exit `2`), distinct from a target-repo condition.

#### Output shape

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

When an anchor omits `symbol`, the output `symbol` field is `null`. The output is
deterministic for a given record set and repo state (fixed key order, stable
input order; no sorting, clock, or RNG).

## Configuration

The MVP core needs no secret. `--require-env NAME` (and the underlying
`msv.env.require_env(name)` helper) is the seam a consumer integration uses to
declare one. Each named variable must be set to a non-empty value; an unset or
empty value is a hard, fail-fast error before any I/O or verification runs —
never a silent default. On the CLI this exits `2`; the helper raises
`RuntimeError`.

## Behavior & guarantees

- **Never imports or executes target-repo code.** Files are read read-only and
  parsed statically — Python with `ast.parse`, JavaScript/TypeScript with
  tree-sitter; nothing in the target repo is imported or run, so a module with an
  import-time side effect (e.g. a top-level `sys.exit(1)`) cannot affect a run.
  Safe against untrusted repositories.
- **Read-only.** No target-repo file is modified and repo mtimes are unchanged.
- **No network. Deterministic** for a given record set and repo state.
- **Verdict precedence** is a single source of truth: `unverifiable` > `stale` >
  `current`.
- **Errors vs. verdicts are distinct.** A target-repo condition becomes a
  verdict; an input-contract or usage problem is an error (CLI exit `2`).

## Running the tests

```
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).
