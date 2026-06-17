"""The one deep module: resolve a single anchor against a repo via AST parse only.

All filesystem and AST knowledge lives here. Callers never see `ast`, `os`, or
`pathlib`. The target repo's code is treated strictly as data: a file is read
read-only and parsed with `ast.parse`; it is never imported or executed, so the
verifier is safe against untrusted repos and against module-top-level side
effects such as `sys.exit`.
"""
from __future__ import annotations

import ast
import os

from msv.types import (
    REASON_FILE_MISSING,
    REASON_NO_SYMBOL_REQUESTED,
    REASON_OK,
    REASON_PARSE_ERROR,
    REASON_PATH_OUTSIDE_REPO,
    REASON_SYMBOL_MISSING,
    Anchor,
    AnchorResult,
)

# AST node types that count as a resolvable module-level or class-body symbol.
_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


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


def _module_symbol_location(tree: ast.Module, symbol: str) -> int | None:
    """Return the 1-based line number of `symbol`, or None if absent.

    A bare name resolves to a function/class declared directly at module top
    level. A dotted "Class.method" resolves to a def declared directly in the
    body of that top-level class (one level deep — nested defs are out of scope).
    """
    if "." in symbol:
        class_name, _, member = symbol.partition(".")
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for child in node.body:
                    if isinstance(child, _DEF_NODES) and child.name == member:
                        return child.lineno
                return None
        return None

    for node in tree.body:
        if isinstance(node, _DEF_NODES) and node.name == symbol:
            return node.lineno
    return None


def resolve_anchor(repo_root: str, anchor: Anchor) -> AnchorResult:
    """Resolve one anchor against repo_root using AST parse only.

    Total function — never raises on expected conditions. Returns an AnchorResult
    whose `found` is True iff the anchor path is inside repo_root, the file exists,
    parses, and (if a symbol is given) the symbol resolves as a module-level
    function/class or "Class.method" in that class body.
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

    try:
        tree = ast.parse(source, filename=abs_path)
    except SyntaxError as exc:
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_PARSE_ERROR}: {exc.msg}",
        )

    if anchor.symbol is None:
        return AnchorResult(
            path=anchor.path,
            symbol=None,
            found=True,
            location=f"{anchor.path}:1",
            reason=REASON_NO_SYMBOL_REQUESTED,
        )

    lineno = _module_symbol_location(tree, anchor.symbol)
    if lineno is None:
        return AnchorResult(
            path=anchor.path,
            symbol=anchor.symbol,
            found=False,
            location=None,
            reason=f"{REASON_SYMBOL_MISSING}: {anchor.symbol}",
        )

    return AnchorResult(
        path=anchor.path,
        symbol=anchor.symbol,
        found=True,
        location=f"{anchor.path}:{lineno}",
        reason=REASON_OK,
    )
