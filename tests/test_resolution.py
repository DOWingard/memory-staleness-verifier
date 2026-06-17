"""Chunk 2: the deep AST resolver. AST parse only — never imports/executes targets."""
from __future__ import annotations

from pathlib import Path

from msv.resolution import resolve_anchor
from msv.types import (
    REASON_FILE_MISSING,
    REASON_NO_SYMBOL_REQUESTED,
    REASON_OK,
    REASON_PARSE_ERROR,
    REASON_PATH_OUTSIDE_REPO,
    REASON_SYMBOL_MISSING,
    Anchor,
)


def test_resolve_file_and_symbol_found(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "refresh"))
    assert res.found is True
    assert res.reason == REASON_OK
    # location is "<repo-relative-path>:<lineno>"; refresh is on line 4.
    assert res.location == "pkg/auth.py:4"
    assert res.path == "pkg/auth.py"
    assert res.symbol == "refresh"


def test_resolve_symbol_none_is_file_presence(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", None))
    assert res.found is True
    assert res.reason == REASON_NO_SYMBOL_REQUESTED
    # With no symbol requested, location points at the file (line 1 sentinel).
    assert res.location == "pkg/auth.py:1"


def test_resolve_class_and_method_found(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "Session.login"))
    assert res.found is True
    assert res.reason == REASON_OK
    # login is defined on line 13 of pkg/auth.py.
    assert res.location == "pkg/auth.py:13"


def test_resolve_async_method_found(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "Session.logout"))
    assert res.found is True
    assert res.reason == REASON_OK


def test_resolve_classdef_as_symbol_found(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "Session"))
    assert res.found is True
    assert res.reason == REASON_OK
    # class Session is defined on line 12.
    assert res.location == "pkg/auth.py:12"


def test_resolve_async_function_found(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "revoke"))
    assert res.found is True
    assert res.reason == REASON_OK


def test_resolve_missing_symbol_reason_names_symbol(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "nonexistent_fn"))
    assert res.found is False
    assert res.location is None
    # reason carries the machine code AND names the missing symbol for evidence.
    assert res.reason.startswith(REASON_SYMBOL_MISSING)
    assert "nonexistent_fn" in res.reason


def test_resolve_missing_method_on_existing_class(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "Session.nope"))
    assert res.found is False
    assert res.reason.startswith(REASON_SYMBOL_MISSING)
    assert "Session.nope" in res.reason


def test_resolve_method_dotted_on_missing_class(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/auth.py", "Ghost.login"))
    assert res.found is False
    assert res.reason.startswith(REASON_SYMBOL_MISSING)


def test_resolve_missing_file_reason(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/does_not_exist.py", "x"))
    assert res.found is False
    assert res.location is None
    assert res.reason.startswith(REASON_FILE_MISSING)


def test_resolve_path_outside_repo_dotdot(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("../escape.py", None))
    assert res.found is False
    assert res.reason.startswith(REASON_PATH_OUTSIDE_REPO)


def test_resolve_path_outside_repo_absolute(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("/etc/passwd", None))
    assert res.found is False
    assert res.reason.startswith(REASON_PATH_OUTSIDE_REPO)


def test_resolve_syntax_error_unverifiable(tmp_repo: Path):
    res = resolve_anchor(str(tmp_repo), Anchor("pkg/broken.py", "oops"))
    assert res.found is False
    assert res.location is None
    assert res.reason.startswith(REASON_PARSE_ERROR)


def test_resolve_is_total_does_not_raise(tmp_repo: Path):
    # Every expected adverse condition returns a populated AnchorResult, never raises.
    for anchor in [
        Anchor("pkg/does_not_exist.py", "x"),
        Anchor("../escape.py", None),
        Anchor("pkg/broken.py", "oops"),
        Anchor("pkg/auth.py", "missing"),
    ]:
        res = resolve_anchor(str(tmp_repo), anchor)
        assert res.found is False
