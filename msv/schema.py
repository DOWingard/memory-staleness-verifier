"""Resolve a memory anchor against a STATIC declared database schema.

Parse-only and language-blind to its caller: given schema source text and a source
kind, build a normalized container/member model and resolve a bare ``T`` (container)
or dotted ``T.C`` (member) into the same status vocabulary ``symbols.locate`` uses.
SQL DDL is parsed by ``sqlglot`` (Postgres dialect) into an AST and folded
(CREATE / ALTER / DROP) in textual order; a ``*.schema.json`` source is parsed by
the stdlib ``json``. No database is ever contacted; sources are data, never executed.

This is the single owner of schema-source parse knowledge. It has no dependency on
``msv.symbols`` (the dispatch seam maps the small ``SchemaResolution`` returned here
onto a ``SymbolLookup``), so it stays pure and testable in isolation.

The absent-vs-indirect rule is the zero-false-stale heart: a container/member is
``missing`` (→ stale) ONLY when it is absent from a closed, fully-parsed, non-open,
non-inheriting, non-uncertain declared schema. Every form of openness — an
undeclared-members-allowed document schema, a ``SELECT *`` view, a ``LIKE`` clone, a
table that ``INHERITS``/partitions, an unmodeled DDL statement, or a source that will
not parse — routes to ``indirect``/``parse_error`` (→ unverifiable), never ``stale``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

SchemaStatus = Literal["found", "missing", "indirect", "parse_error"]

# Source kinds the dispatch in symbols.py may pass.
SQL = "sql"
JSON_SCHEMA = "json_schema"


@dataclass(frozen=True, slots=True)
class Container:
    """A declared relation/collection and the members provably present in it."""

    name: str
    kind: str  # "table" | "view" | "collection"
    members: frozenset[str]  # column / field names provably present
    lineno: int | None  # best-effort declaration line; evidence only
    open: bool  # undeclared members allowed → member absence NOT provable
    inherits: bool  # unresolved parent (INHERITS / partition) → member maybe inherited
    uncertain: bool  # an unmodeled DDL action touched it → its members not provable


@dataclass(frozen=True, slots=True)
class SchemaModel:
    """The normalized schema: named containers plus namespace-openness flags."""

    containers: dict[str, Container]
    open_namespace: bool  # source admits undeclared CONTAINERS → container absence not provable
    # A single anonymous object schema (one document collection per file) resolves
    # against this lone container for ANY anchor name — container existence for a
    # one-collection file is trivially true; the valuable check is at the member level.
    solitary: Container | None = None


@dataclass(frozen=True, slots=True)
class SchemaResolution:
    """Outcome of resolving one symbol against a schema source.

    `detail` names the indirection mechanism for an `indirect` status:
    `open_schema` | `maybe_inherited` | `uncertain_ddl` | `dynamic_namespace`.
    """

    status: SchemaStatus
    lineno: int | None = None
    detail: str | None = None


def build_model(source: str, source_kind: str) -> SchemaModel | None:
    """Parse a schema source into a normalized model, or None if it cannot parse.

    None routes to `parse_error` (→ unverifiable); a returned model is always a
    clean parse against which absence may be provable. Total — never raises on
    expected conditions.
    """
    if source_kind == JSON_SCHEMA:
        return _build_json_model(source)
    # SQL lands in a following commit; an unknown kind has no model.
    return None


def resolve_symbol(source: str, source_kind: str, symbol: str | None) -> SchemaResolution:
    """Build the model and resolve `symbol` (None | 'T' | 'T.C').

    Total — never raises on expected conditions. An unparseable source is
    `parse_error`; every uncertainty routes to `indirect`, never `missing`.
    """
    model = build_model(source, source_kind)
    if model is None:
        return SchemaResolution(status="parse_error")
    if symbol is None:
        return SchemaResolution(status="found", lineno=1)
    return _resolve_in_model(model, symbol)


def _resolve_in_model(model: SchemaModel, symbol: str) -> SchemaResolution:
    """Apply the absent-vs-indirect rule for a bare 'T' or dotted 'T.C'."""
    container_name, dot, member = symbol.partition(".")
    container = _lookup_container(model, container_name)
    if not dot:
        # Bare container T.
        if container is not None:
            return SchemaResolution(status="found", lineno=container.lineno)
        if model.open_namespace:
            return SchemaResolution(status="indirect", detail="dynamic_namespace")
        return SchemaResolution(status="missing")
    # Dotted member T.C.
    if container is None:
        if model.open_namespace:
            return SchemaResolution(status="indirect", detail="dynamic_namespace")
        # The container itself is provably absent → the column claim is stale.
        return SchemaResolution(status="missing")
    if member in container.members:
        return SchemaResolution(status="found", lineno=container.lineno)
    if container.open:
        # Undeclared members are permitted (SELECT * view, LIKE clone, open
        # document schema) → member absence is not provable.
        return SchemaResolution(status="indirect", detail="open_schema")
    if container.uncertain:
        # An unmodeled DDL action touched the container → its members are not
        # provably complete.
        return SchemaResolution(status="indirect", detail="uncertain_ddl")
    if container.inherits:
        # A member may come from an unresolved parent/partition.
        return SchemaResolution(status="indirect", detail="maybe_inherited")
    return SchemaResolution(status="missing")


def _lookup_container(model: SchemaModel, name: str) -> Container | None:
    if model.solitary is not None:
        return model.solitary
    return model.containers.get(name)


# --- JSON-Schema / Mongo $jsonSchema source ----------------------------------

# Keys whose presence marks an object as a JSON-Schema (vs a {name: schema} map).
_SCHEMA_KEYWORDS = frozenset(
    {"properties", "type", "bsonType", "required", "additionalProperties",
     "patternProperties", "$schema"}
)


def _build_json_model(source: str) -> SchemaModel | None:
    """Parse a JSON-Schema / Mongo $jsonSchema source into a SchemaModel.

    A single object schema becomes one anonymous (solitary) container; a
    `{name: schema}` map becomes one named container per key. A non-object root,
    or text that is neither a schema nor a clean map, is None (→ parse_error) —
    never an empty model that could false-stale.
    """
    try:
        data = json.loads(source)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    inner = data.get("$jsonSchema")
    root = inner if isinstance(inner, dict) else data
    if _looks_like_schema(root):
        return SchemaModel(
            containers={}, open_namespace=False,
            solitary=_build_json_container("", root, 1),
        )
    if data and all(isinstance(value, dict) for value in data.values()):
        containers = {
            key: _build_json_container(key, _unwrap_jsonschema(value), _json_lineno(source, key))
            for key, value in data.items()
        }
        return SchemaModel(containers=containers, open_namespace=False)
    return None


def _looks_like_schema(obj: dict) -> bool:
    return any(keyword in obj for keyword in _SCHEMA_KEYWORDS)


def _unwrap_jsonschema(obj: dict) -> dict:
    inner = obj.get("$jsonSchema")
    return inner if isinstance(inner, dict) else obj


def _build_json_container(name: str, obj: dict, lineno: int | None) -> Container:
    """Model one document schema: its declared fields and whether it is open."""
    props = obj.get("properties")
    if isinstance(props, dict):
        members = frozenset(props.keys())
        # JSON-Schema additionalProperties DEFAULTS to true (open). It is closed
        # only when explicitly false AND no patternProperties admits extra keys.
        is_open = not (
            obj.get("additionalProperties") is False and not obj.get("patternProperties")
        )
    else:
        # No enumerable `properties` → members cannot be listed → open.
        members = frozenset()
        is_open = True
    return Container(
        name=name, kind="collection", members=members, lineno=lineno,
        open=is_open, inherits=False, uncertain=False,
    )


def _json_lineno(source: str, name: str) -> int | None:
    """Best-effort 1-based line of the first occurrence of the quoted `name` key."""
    needle = f'"{name}"'
    for index, line in enumerate(source.splitlines(), start=1):
        if needle in line:
            return index
    return None
