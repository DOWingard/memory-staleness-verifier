"""Resolve a single anchor to a location in a repo, safely and read-only.

This module owns filesystem and path-containment knowledge; all language and
parsing knowledge lives in `msv.symbols`. A target file is read read-only and
handed to the symbol seam as text — never imported or executed — so the verifier
is safe against untrusted repos and against module-top-level side effects.
"""
from __future__ import annotations

import os

from msv import symbols
from msv.symbols import SymbolLookup
from msv.types import (
    REASON_FILE_MISSING,
    REASON_NO_SYMBOL_REQUESTED,
    REASON_OK,
    REASON_PARSE_ERROR,
    REASON_PATH_OUTSIDE_REPO,
    REASON_SYMBOL_MISSING,
    REASON_UNSUPPORTED_LANGUAGE,
    Anchor,
    AnchorResult,
)


def _within_repo(repo_root: str, rel_path: str) -> str | None:
    """Return the absolute path of rel_path iff it is contained in repo_root.

    Containment is decided after resolving symlinks and `..` on both sides via
    realpath + commonpath, so traversal and symlink escapes are rejected.
    Returns None when the path escapes the repository.
    """
    root_abs = os.path.realpath(repo_root)
    candidate_abs = os.path.realpath(os.path.join(root_abs, rel_path))
    try:
        common = os.path.commonpath([root_abs, candidate_abs])
    except ValueError:
        # Different drives / mixed absolute-relative on some platforms.
        return None
    if common != root_abs:
        return None
    return candidate_abs


def resolve_anchor(repo_root: str, anchor: Anchor) -> AnchorResult:
    """Resolve one anchor against repo_root, reading the target as data only.

    Total function — never raises on expected conditions. Returns an AnchorResult
    whose `found` is True iff the anchor path is inside repo_root, the file exists,
    parses, and (if a symbol is given) the symbol resolves in that file's language.
    """
    abs_path = _within_repo(repo_root, anchor.path)
    if abs_path is None:
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_PATH_OUTSIDE_REPO}: {anchor.path}",
        )

    if not os.path.isfile(abs_path):
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_FILE_MISSING}: {anchor.path}",
        )

    with open(abs_path, "r", encoding="utf-8") as handle:
        source = handle.read()

    lookup = symbols.locate(source, anchor.path, anchor.symbol)
    return _to_anchor_result(anchor, lookup)


def _to_anchor_result(anchor: Anchor, lookup: SymbolLookup) -> AnchorResult:
    """Map a structural SymbolLookup onto the reason-coded AnchorResult."""
    if lookup.status == "unsupported":
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_UNSUPPORTED_LANGUAGE}: {anchor.path}",
        )

    if lookup.status == "parse_error":
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_PARSE_ERROR}: {lookup.detail or 'syntax error'}",
        )

    if lookup.status == "missing":
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_SYMBOL_MISSING}: {anchor.symbol}",
        )

    # status == "found"
    if anchor.symbol is None:
        return AnchorResult(
            path=anchor.path,
            symbol=None,
            found=True,
            location=f"{anchor.path}:1",
            reason=REASON_NO_SYMBOL_REQUESTED,
        )
    return AnchorResult(
        path=anchor.path,
        symbol=anchor.symbol,
        found=True,
        location=f"{anchor.path}:{lookup.lineno}",
        reason=REASON_OK,
    )
