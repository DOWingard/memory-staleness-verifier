"""Contract tests for the schema-source resolver (msv/schema.py) and its dispatch.

Pure, filesystem-free tests against `schema.resolve_symbol` and the `symbols.locate`
routing seam. The dispatch tests pin the suffix gate — including the no-regression
boundary that keeps a bare `.json` file unsupported. The per-source tests pin the
absent-vs-indirect rule that is the zero-false-stale heart for schema targets: a
container/member is `missing` (→ stale) only when it is absent from a closed,
fully-parsed, non-open, non-inheriting, non-uncertain declared schema; every form
of openness or uncertainty routes to `indirect`/`parse_error` (→ unverifiable).
"""
from __future__ import annotations

from msv import schema, symbols


# --- dispatch: which file suffixes route to the schema resolver ---------------


def test_sql_extension_routes_to_schema():
    # A .sql file is resolved by the schema seam, never reported unsupported.
    lookup = symbols.locate("CREATE TABLE users (id int);", "db/schema.sql", "users")
    assert lookup.status != "unsupported"


def test_schema_json_suffix_routes_to_schema():
    lookup = symbols.locate(
        '{"properties": {"id": {}}}', "db/users.schema.json", "users"
    )
    assert lookup.status != "unsupported"


def test_bare_json_still_unsupported():
    # The shipped contract: a bare .json file is unsupported (never read as a schema).
    lookup = symbols.locate('{"k": 1}', "src/data.json", None)
    assert lookup.status == "unsupported"
