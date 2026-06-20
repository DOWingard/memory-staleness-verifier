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


# --- JSON-Schema / Mongo $jsonSchema source -----------------------------------


def _json(source: str, symbol: str | None):
    return schema.resolve_symbol(source, schema.JSON_SCHEMA, symbol)


def test_json_present_field_is_found():
    r = _json('{"properties": {"email": {}, "id": {}}}', "users.email")
    assert r.status == "found"


def test_json_container_named_for_file_stem():
    # A single object schema is one container that matches any anchor name; the
    # member is what is actually resolved.
    src = '{"properties": {"email": {}}, "additionalProperties": false}'
    assert _json(src, "users").status == "found"
    assert _json(src, "users.email").status == "found"


def test_json_additionalprops_false_absent_field_is_missing():
    # A closed document schema: an absent field is provably absent -> missing (stale).
    src = '{"properties": {"id": {}}, "additionalProperties": false}'
    r = _json(src, "users.phone")
    assert r.status == "missing"


def test_json_default_open_absent_field_is_indirect():
    # JSON-Schema additionalProperties DEFAULTS to true: an absent field in a
    # schema with no explicit additionalProperties is NOT provably absent.
    r = _json('{"properties": {"id": {}}}', "users.phone")
    assert r.status == "indirect"
    assert r.detail == "open_schema"


def test_json_dollar_jsonschema_unwrapped():
    # A Mongo validator wraps the schema in $jsonSchema; fields resolve through it.
    src = (
        '{"$jsonSchema": {"bsonType": "object", '
        '"properties": {"email": {}}, "additionalProperties": false}}'
    )
    assert _json(src, "users.email").status == "found"
    assert _json(src, "users.phone").status == "missing"


def test_json_map_of_collections():
    # A {name: schema} map declares one container per key.
    src = (
        '{"users": {"properties": {"email": {}}, "additionalProperties": false}, '
        '"orders": {"properties": {"total": {}}, "additionalProperties": false}}'
    )
    assert _json(src, "users").status == "found"
    assert _json(src, "orders.total").status == "found"
    assert _json(src, "orders.shipping").status == "missing"


def test_json_absent_container_in_map_is_missing():
    src = '{"users": {"properties": {"email": {}}, "additionalProperties": false}}'
    assert _json(src, "customers").status == "missing"
    assert _json(src, "customers.x").status == "missing"


def test_json_no_properties_key_is_open():
    # A schema with no `properties` cannot enumerate members -> absence unprovable.
    r = _json('{"type": "object", "additionalProperties": false}', "users.email")
    assert r.status == "indirect"
    assert r.detail == "open_schema"


def test_json_malformed_is_parse_error():
    assert _json("{not valid json", "users.email").status == "parse_error"


def test_json_non_object_root_is_parse_error():
    # An array / scalar root is not a schema object -> unverifiable, never missing.
    assert _json("[1, 2, 3]", "users.email").status == "parse_error"


def test_json_symbol_none_is_file_presence():
    r = _json('{"properties": {"id": {}}}', None)
    assert r.status == "found"
    assert r.lineno == 1
