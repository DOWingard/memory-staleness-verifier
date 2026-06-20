"""resolve_anchor against JS/TS repos: full path -> AnchorResult behavior."""
from __future__ import annotations

from pathlib import Path

from msv.resolution import resolve_anchor
from msv.types import (
    REASON_NO_SYMBOL_REQUESTED,
    REASON_OK,
    REASON_PARSE_ERROR,
    REASON_SYMBOL_MISSING,
    REASON_UNSUPPORTED_LANGUAGE,
    Anchor,
)


def test_ts_function_found_with_location(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "refresh"))
    assert res.found is True
    assert res.reason == REASON_OK
    assert res.location == "src/auth.ts:1"


def test_ts_arrow_const_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "revoke"))
    assert res.found is True
    assert res.location == "src/auth.ts:5"


def test_ts_class_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "Session"))
    assert res.found is True
    assert res.location == "src/auth.ts:9"


def test_ts_method_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "Session.login"))
    assert res.found is True
    assert res.location == "src/auth.ts:10"


def test_ts_async_method_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "Session.logout"))
    assert res.found is True
    assert res.location == "src/auth.ts:14"


def test_ts_symbol_none_is_file_presence(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", None))
    assert res.found is True
    assert res.reason == REASON_NO_SYMBOL_REQUESTED
    assert res.location == "src/auth.ts:1"


def test_ts_data_const_is_symbol_missing(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "MAX_AGE"))
    assert res.found is False
    assert res.reason.startswith(REASON_SYMBOL_MISSING)


def test_ts_interface_is_symbol_missing(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "User"))
    assert res.found is False
    assert res.reason.startswith(REASON_SYMBOL_MISSING)


def test_ts_type_alias_is_symbol_missing(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "Id"))
    assert res.found is False
    assert res.reason.startswith(REASON_SYMBOL_MISSING)


def test_ts_enum_is_symbol_missing(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/auth.ts", "Role"))
    assert res.found is False
    assert res.reason.startswith(REASON_SYMBOL_MISSING)


def test_tsx_arrow_component_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/component.tsx", "Button"))
    assert res.found is True
    assert res.location == "src/component.tsx:1"


def test_tsx_default_component_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/component.tsx", "App"))
    assert res.found is True
    assert res.location == "src/component.tsx:5"


def test_js_function_arrow_method(tmp_ts_repo: Path):
    repo = str(tmp_ts_repo)
    assert resolve_anchor(repo, Anchor("src/util.js", "helper")).location == "src/util.js:1"
    assert resolve_anchor(repo, Anchor("src/util.js", "arrow")).location == "src/util.js:4"
    assert resolve_anchor(repo, Anchor("src/util.js", "Widget.render")).location == "src/util.js:6"


def test_dts_ambient_function_found(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("types/api.d.ts", "fetchUser"))
    assert res.found is True
    assert res.location == "types/api.d.ts:1"


def test_dts_ambient_class_and_method_found(tmp_ts_repo: Path):
    repo = str(tmp_ts_repo)
    assert resolve_anchor(repo, Anchor("types/api.d.ts", "Client")).found is True
    assert resolve_anchor(repo, Anchor("types/api.d.ts", "Client.send")).found is True


def test_ts_clean_symbol_found_despite_error(tmp_ts_repo: Path):
    # `good` parses cleanly even though `bad` below it is a syntax error.
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/broken.ts", "good"))
    assert res.found is True
    assert res.location == "src/broken.ts:1"


def test_ts_symbol_in_error_region_is_parse_error(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/broken.ts", "bad"))
    assert res.found is False
    assert res.reason.startswith(REASON_PARSE_ERROR)


def test_ts_absent_name_in_broken_file_is_parse_error(tmp_ts_repo: Path):
    # Absence in an unparseable file is unverifiable, not a deletion signal.
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/broken.ts", "never_here"))
    assert res.found is False
    assert res.reason.startswith(REASON_PARSE_ERROR)


def test_unsupported_file_type(tmp_ts_repo: Path):
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/data.json", None))
    assert res.found is False
    assert res.reason.startswith(REASON_UNSUPPORTED_LANGUAGE)


def test_python_file_in_same_repo_still_resolves(tmp_ts_repo: Path):
    # The .py path goes through the ast backend even in a JS/TS repo.
    res = resolve_anchor(str(tmp_ts_repo), Anchor("src/legacy.py", "old"))
    assert res.found is True
    assert res.location == "src/legacy.py:1"
