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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SchemaStatus = Literal["found", "missing", "indirect", "parse_error"]

# Source kinds the dispatch in symbols.py may pass.
SQL = "sql"
JSON_SCHEMA = "json_schema"


@dataclass(frozen=True, slots=True)
class SchemaResolution:
    """Outcome of resolving one symbol against a schema source.

    `detail` names the indirection mechanism for an `indirect` status:
    `open_schema` | `maybe_inherited` | `uncertain_ddl` | `dynamic_namespace`.
    """

    status: SchemaStatus
    lineno: int | None = None
    detail: str | None = None


def resolve_symbol(source: str, source_kind: str, symbol: str | None) -> SchemaResolution:
    """Build the model and resolve `symbol` (None | 'T' | 'T.C').

    Total — never raises on expected conditions. An unparseable source is
    `parse_error`; every uncertainty routes to `indirect`, never `missing`.
    """
    return SchemaResolution(status="parse_error")
