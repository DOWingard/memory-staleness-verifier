"""Chunk 3: per-record verdict policy. unverifiable > stale > current."""
from __future__ import annotations

from pathlib import Path

from msv.verdict import verify_record


def test_verify_record_all_found_is_current(tmp_repo: Path, make_record):
    rec = make_record("m1", ("pkg/auth.py", "refresh"), ("pkg/parser.py", "parse"))
    rv = verify_record(str(tmp_repo), rec)
    assert rv.id == "m1"
    assert rv.verdict == "current"
    assert all(a.found for a in rv.anchors)
    assert len(rv.anchors) == 2


def test_verify_record_missing_symbol_is_stale(tmp_repo: Path, make_record):
    # File present, symbol gone -> stale (not unverifiable, not current).
    rec = make_record("m2", ("pkg/auth.py", "renamed_away"))
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "stale"


def test_verify_record_missing_file_is_stale(tmp_repo: Path, make_record):
    rec = make_record("m3", ("pkg/deleted.py", "anything"))
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "stale"


def test_verify_record_no_anchors_unverifiable(tmp_repo: Path, make_record):
    rec = make_record("m4")  # zero anchors
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "unverifiable"
    assert rv.anchors == ()


def test_verify_record_outside_repo_unverifiable(tmp_repo: Path, make_record):
    rec = make_record("m5", ("../escape.py", None))
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "unverifiable"


def test_verify_record_parse_error_unverifiable(tmp_repo: Path, make_record):
    rec = make_record("m6", ("pkg/broken.py", "oops"))
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "unverifiable"


def test_verify_record_precedence_unverifiable_dominates_stale(tmp_repo: Path, make_record):
    # One stale anchor (missing file) + one unverifiable anchor (parse error).
    # Precedence: the record is unverifiable, not stale.
    rec = make_record(
        "m7",
        ("pkg/deleted.py", "x"),      # stale-signal
        ("pkg/broken.py", "oops"),    # unverifiable-signal
    )
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "unverifiable"


def test_verify_record_precedence_stale_dominates_current(tmp_repo: Path, make_record):
    # One found anchor + one missing-symbol anchor -> stale (not current).
    rec = make_record(
        "m8",
        ("pkg/auth.py", "refresh"),   # found
        ("pkg/auth.py", "gone"),      # stale-signal
    )
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "stale"


def test_verify_record_outside_repo_dominates_missing_file(tmp_repo: Path, make_record):
    rec = make_record(
        "m9",
        ("pkg/deleted.py", "x"),      # stale-signal (file_missing)
        ("/etc/passwd", None),        # unverifiable-signal (path_outside_repo)
    )
    rv = verify_record(str(tmp_repo), rec)
    assert rv.verdict == "unverifiable"


def test_verify_record_preserves_anchor_order(tmp_repo: Path, make_record):
    rec = make_record(
        "m10",
        ("pkg/parser.py", "parse"),
        ("pkg/auth.py", "refresh"),
        ("pkg/deleted.py", "x"),
    )
    rv = verify_record(str(tmp_repo), rec)
    assert [a.path for a in rv.anchors] == [
        "pkg/parser.py", "pkg/auth.py", "pkg/deleted.py",
    ]


# --- JS/TS verdicts -----------------------------------------------------------


def test_verify_ts_record_all_found_is_current(tmp_ts_repo: Path, make_record):
    rec = make_record("t1", ("src/auth.ts", "refresh"), ("src/component.tsx", "Button"))
    assert verify_record(str(tmp_ts_repo), rec).verdict == "current"


def test_verify_ts_missing_symbol_is_stale(tmp_ts_repo: Path, make_record):
    # An interface is not in the resolvable set: the name is absent -> stale.
    rec = make_record("t2", ("src/auth.ts", "User"))
    assert verify_record(str(tmp_ts_repo), rec).verdict == "stale"


def test_verify_ts_found_despite_error_is_current(tmp_ts_repo: Path, make_record):
    rec = make_record("t3", ("src/broken.ts", "good"))
    assert verify_record(str(tmp_ts_repo), rec).verdict == "current"


def test_verify_ts_error_region_symbol_is_unverifiable(tmp_ts_repo: Path, make_record):
    rec = make_record("t4", ("src/broken.ts", "bad"))
    assert verify_record(str(tmp_ts_repo), rec).verdict == "unverifiable"


def test_verify_unsupported_file_is_unverifiable(tmp_ts_repo: Path, make_record):
    rec = make_record("t5", ("src/data.json", None))
    assert verify_record(str(tmp_ts_repo), rec).verdict == "unverifiable"


def test_verify_unsupported_dominates_stale(tmp_ts_repo: Path, make_record):
    # Precedence: an unsupported anchor makes the record unverifiable even
    # alongside a stale (missing-symbol) anchor.
    rec = make_record(
        "t6",
        ("src/auth.ts", "User"),     # stale-signal (missing)
        ("src/data.json", None),     # unverifiable-signal (unsupported)
    )
    assert verify_record(str(tmp_ts_repo), rec).verdict == "unverifiable"


def test_verify_mixed_python_and_ts_record_is_current(tmp_ts_repo: Path, make_record):
    rec = make_record("t7", ("src/auth.ts", "refresh"), ("src/legacy.py", "old"))
    assert verify_record(str(tmp_ts_repo), rec).verdict == "current"
