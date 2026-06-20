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

- `current` — every anchor resolves: the file exists and, if a symbol is given,
  it resolves as a callable and (when a fingerprint is recorded) its call shape
  is unchanged or only additively changed.
- `stale` — at least one anchor is provably broken: its file or symbol is gone
  (the name is bound nowhere in a cleanly-parsed file, including a symbol deleted
  at the source of a re-export `msv` follows), or a recorded interface
  fingerprint shows the symbol's call shape changed in a call-breaking way.
- `unverifiable` — nothing is provably broken, but at least one anchor cannot be
  decided: the record has no anchors, an anchor path is outside the repo, a file
  cannot be parsed or its language is unsupported, the symbol is present only
  indirectly (a re-export `msv` cannot follow — a wildcard/barrel, a bare or
  absolute specifier, or a further hop — a data/type declaration, or a nested or
  possibly-inherited definition), or a recorded fingerprint cannot be compared
  (a future version, or an overloaded symbol).

Precedence (one source of truth): `unverifiable` > `stale` > `current`.

`stale` fires only on a provable mechanical mismatch; every uncertainty routes to
`unverifiable`. A still-correct memory is therefore never flagged `stale` — at
the cost of occasionally returning `unverifiable` for a fact that is in truth
out of date.

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
`f`. Type-only and value-only declarations are not resolvable callables, but the
name is present, so an anchor to one is reported `symbol_indirect`
(`unverifiable`), never missing: TypeScript `interface`, `type`, and `enum`, and
non-function constants such as `const MAX = 5`. A file whose extension is not in
the table is reported `unsupported_language` (an `unverifiable` verdict).

For JavaScript/TypeScript a syntax error in one part of a file does not hide
cleanly-parsed declarations elsewhere; a name that cannot be cleanly located in a
file that fails to parse is reported `unverifiable`, never missing, so a syntax
error never reads as a deletion. Resolution is structural, not semantic: it
confirms a declaration with that name still exists. A symbol that arrives through
a single named, relative re-export is followed one hop to its source (see
[One-hop re-export following](#one-hop-re-export-following)); every other
indirection is reported `symbol_indirect` (`unverifiable`), never stale.

## One-hop re-export following

A barrel or re-export module exposes a name that is really declared elsewhere —
`from .core import parse`, `export { Button } from './Button'`. By existence
alone the name is only present *indirectly*, so such an anchor would be
`unverifiable`. `msv` follows exactly **one** named, relative re-export/import
edge to the source file and resolves the original declaration there, turning a
class of `unverifiable` results into precise `current` / `stale`:

- the re-export still resolves to a declaration at its source → `current`;
- the symbol has been **deleted at its source** (bound nowhere in the resolved
  target, and not a submodule of the package) → `stale` (`symbol_missing`, with
  the resolved source named as `… (via pkg/core.py)`);
- the symbol's **source call shape drifts** in a call-breaking way, when a
  fingerprint was recorded → `stale` (`signature_changed`).

When a re-export is followed, `location` points at the **source** declaration
(e.g. `pkg/core.py:42`), not the re-exporting file. The fingerprint baseline is
minted through the same hop, so capture and verify always describe the same
declaration.

Following is **relative and named only**, one hop, and stays inside the repo;
every uncertainty keeps the original `unverifiable`, so the zero-false-`stale`
guarantee is unchanged. A new `stale` arises only from a clean landing on a
single in-repo target. The following are **not** followed and remain
`symbol_indirect` (`unverifiable`):

- wildcard / star re-exports (`from .x import *`, `export * from './x'`) — the
  source module is ambiguous;
- bare or absolute specifiers (`from pkg.core import x`, `import x from 'lib'`),
  and TypeScript `paths` / package `exports` aliases — these need module-search
  configuration `msv` does not read;
- two or more hops — if the source is itself a re-export, following stops;
- higher-order wrappers (`memo(X)`, `forwardRef(X)`, `styled.button`) — a
  same-file value expression, not a cross-file edge.

## Interface fingerprints (call-shape drift)

Symbol existence alone misses a whole class of staleness: a memory like "`parse`
takes three arguments" stays *current* by existence even after `parse` drops an
argument. An optional, opt-in interface fingerprint closes that gap without ever
risking a false `stale`.

The flow has two halves:

1. **Capture.** When a memory is recorded, the consumer calls
   `fingerprint_anchor(repo, anchor)` and persists the returned opaque token on
   the anchor (e.g. in its `fingerprint` field). The token encodes the symbol's
   call shape — arity, required vs optional parameters, `*args`/rest and
   `**kwargs`, generator and async/await form, call-convention decorators
   (`property`/`staticmethod`/`classmethod`; `static`/`getter`/`setter`), and
   base-class count.
2. **Verify.** When the record is later checked, msv re-derives the current call
   shape and compares it to the recorded token.

The comparison is **directional**: it flags drift only when a call that was valid
under the recorded shape would now be invalid (a required argument added, the
positional capacity dropped below what was required, `**kwargs` removed, a
sync↔async or generator switch, a call-convention decorator toggled, a base
removed). Purely additive changes — a new optional parameter, a new
`*args`/`**kwargs`, a new base — never flag. Drift is reported `signature_changed`
(verdict `stale`) with the symbol still `found` and `location` populated, so the
evidence is preserved.

Anything the comparison cannot decide routes to `unverifiable`, never `stale`: a
token minted under a **future format version** msv cannot parse
(`fingerprint_version_mismatch`), or an **overloaded / multiply-declared** symbol
whose shape is ambiguous (`fingerprint_version_mismatch: ambiguous_overload`).

> **Capture precondition.** `fingerprint_anchor` must be called **synchronously
> at capture**, against the same working tree the agent saw. The token is the
> baseline; minting it later, against a tree that has already drifted, would bake
> the drift into the baseline and defeat the guarantee. msv mints from the exact
> file bytes on disk — never reconstructed from a commit — so a dirty working
> tree never produces a false baseline.

```python
from msv import Anchor, Record, fingerprint_anchor, verify_records

anchor = Anchor(path="pkg/parser.py", symbol="parse")
token = fingerprint_anchor("/path/to/repo", anchor)        # at capture
stored = Anchor(path=anchor.path, symbol=anchor.symbol, fingerprint=token)

# ...later, after the code may have changed...
verdicts, summary = verify_records("/path/to/repo", [
    Record(id="m1", claim_text="parse takes three args", anchors=(stored,)),
])
```

A fingerprint is honored only alongside a `symbol`; an anchor with a fingerprint
but no symbol is inert. The token is opaque — treat it as a blob, never parse it.

## API / Reference

Import the public surface from the top-level package:

```python
from msv import (
    verify_records, verify_record, resolve_anchor, fingerprint_anchor,
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
symbol resolves in that file's language. When the anchor carries a `fingerprint`
and the symbol resolves, the recorded call shape is compared (see
[Interface fingerprints](#interface-fingerprints-call-shape-drift)).

```python
fingerprint_anchor(repo_root: str, anchor: Anchor) -> str | None
```
The capture seam. Resolves the anchor read-only — following one re-export hop to
its source if needed — and returns an opaque call-shape token when the symbol
resolves to a single callable, else `None` (no symbol; the symbol is absent,
indirect, or overloaded; the file is missing, unparseable, or unsupported; or the
path escapes the repo). A total function — never raises. Call
it **synchronously at capture**, against the working tree the agent saw; see
[Interface fingerprints](#interface-fingerprints-call-shape-drift).

### Data types

All data types are frozen dataclasses; `Verdict` is the literal
`"current" | "stale" | "unverifiable"`.

```python
Anchor(path: str, symbol: str | None = None, fingerprint: str | None = None)
```
`path` is repo-relative; its extension selects the language. `symbol` is a
top-level function/class name, or a dotted `"Class.method"` resolved one level
deep into the top-level class body (nested defs are out of scope). See
[Supported languages](#supported-languages) for the per-language symbol forms.
`fingerprint` is an opaque, msv-minted call-shape token (see
[Interface fingerprints](#interface-fingerprints-call-shape-drift)); it is
honored only alongside a `symbol`, and a fingerprint with no symbol is inert.

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
`location` is e.g. `"pkg/auth.py:42"` when found, else `None` — but it stays
populated for `signature_changed`, where the symbol exists and only its shape
drifted, and points at the **source** file when a re-export was followed.
`reason` is a machine-stable code, optionally with a `: <detail>`
suffix — one of: `ok`, `no_symbol_requested`, `file_missing`, `symbol_missing`,
`symbol_indirect`, `signature_changed`, `fingerprint_version_mismatch`,
`path_outside_repo`, `parse_error`, `unsupported_language`.

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
