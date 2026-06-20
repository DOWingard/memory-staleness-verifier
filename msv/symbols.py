"""All language and parse knowledge: locate a symbol in source text.

This is the one module that knows how each supported language is parsed. Python
is handled by the stdlib `ast`; JavaScript/TypeScript by tree-sitter grammars.
Source is treated strictly as data — parsed, never imported or executed — so the
verifier stays safe against untrusted repositories.

The public seam is `locate(source, path, symbol) -> SymbolLookup`. The language
is inferred from the path extension; callers never name a language.

tree-sitter is error-recovering: a malformed file still yields a tree with ERROR
nodes instead of raising. The resolution policy is therefore "found-despite-
error" — a symbol whose own declaration parses cleanly resolves even when another
region of the file is broken, while a name that cannot be cleanly located in a
file that failed to parse is reported parse_error (unverifiable), never missing.
A syntax error thus never masquerades as a deleted symbol.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Iterator, Literal

import tree_sitter_javascript as _ts_javascript
import tree_sitter_typescript as _ts_typescript
from tree_sitter import Language, Node, Parser

LookupStatus = Literal["found", "missing", "parse_error", "unsupported"]


@dataclass(frozen=True, slots=True)
class SymbolLookup:
    status: LookupStatus
    lineno: int | None = None  # 1-based; 1 for a file-presence (symbol=None) hit
    detail: str | None = None  # parser message when status == "parse_error"


# Internal language ids. Extension -> id; the id selects the parser backend and
# is the single source of which file types the verifier can resolve.
_PYTHON = "python"
_LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": _PYTHON,
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
}

# tree-sitter Language objects and reusable parsers, built once per grammar.
_TS_LANGUAGES: dict[str, Language] = {
    "javascript": Language(_ts_javascript.language()),
    "typescript": Language(_ts_typescript.language_typescript()),
    "tsx": Language(_ts_typescript.language_tsx()),
}
_PARSERS: dict[str, Parser] = {name: Parser(lang) for name, lang in _TS_LANGUAGES.items()}

# tree-sitter node types that declare a top-level function by name (the last is
# the bodiless form found in .d.ts ambient declarations).
_TS_FUNCTION_NODES = frozenset(
    {"function_declaration", "generator_function_declaration", "function_signature"}
)
# ...that declare a top-level class by name.
_TS_CLASS_NODES = frozenset({"class_declaration", "abstract_class_declaration"})
# ...that declare a member inside a class body (the last is the .d.ts form).
_TS_METHOD_NODES = frozenset({"method_definition", "method_signature"})
# Initializer node types that make a const/let/var binding "function-shaped",
# mirroring Python's def/class-only model.
_TS_FUNCTION_VALUES = frozenset(
    {"arrow_function", "function_expression", "function", "generator_function"}
)
# Wrappers that are transparent to top-level declaration lookup: `export`,
# `export default`, and `declare` should not hide the declaration they carry.
_TS_BINDING_NODES = frozenset({"lexical_declaration", "variable_declaration"})
_TS_EXPORT = "export_statement"
_TS_AMBIENT = "ambient_declaration"


def locate(source: str, path: str, symbol: str | None) -> SymbolLookup:
    """Find `symbol` in `source`, choosing a parser from `path`'s extension.

    A bare symbol resolves to a top-level function or class, or a const/let/var
    bound to a function/arrow. A dotted "Class.method" resolves to a method in
    that top-level class's body. When `symbol` is None the result reports only
    that the file is present and parses. An unknown extension yields status
    "unsupported"; a file that will not parse yields "parse_error".
    """
    language = _language_for_path(path)
    if language is None:
        return SymbolLookup(status="unsupported")
    if language == _PYTHON:
        return _locate_python(source, path, symbol)
    return _locate_treesitter(source, symbol, language)


def _language_for_path(path: str) -> str | None:
    _root, ext = os.path.splitext(path)
    return _LANGUAGE_BY_EXT.get(ext.lower())


# --- Python (stdlib ast) -----------------------------------------------------

_PY_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _locate_python(source: str, path: str, symbol: str | None) -> SymbolLookup:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return SymbolLookup(status="parse_error", detail=exc.msg)
    if symbol is None:
        return SymbolLookup(status="found", lineno=1)
    lineno = _python_symbol_lineno(tree, symbol)
    if lineno is None:
        return SymbolLookup(status="missing")
    return SymbolLookup(status="found", lineno=lineno)


def _python_symbol_lineno(tree: ast.Module, symbol: str) -> int | None:
    """1-based line of a top-level def/class, or a one-level "Class.method"."""
    if "." in symbol:
        class_name, _, member = symbol.partition(".")
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for child in node.body:
                    if isinstance(child, _PY_DEF_NODES) and child.name == member:
                        return child.lineno
                return None
        return None
    for node in tree.body:
        if isinstance(node, _PY_DEF_NODES) and node.name == symbol:
            return node.lineno
    return None


# --- JavaScript / TypeScript (tree-sitter) -----------------------------------


def _locate_treesitter(source: str, symbol: str | None, language: str) -> SymbolLookup:
    root = _PARSERS[language].parse(source.encode("utf-8")).root_node

    if symbol is None:
        if root.has_error:
            return SymbolLookup(status="parse_error", detail="syntax error")
        return SymbolLookup(status="found", lineno=1)

    node = _find_ts_symbol(root, symbol)
    if node is not None and not node.has_error:
        return SymbolLookup(status="found", lineno=node.start_point[0] + 1)
    # Not cleanly located. A name that is absent only because the parse failed
    # (the error may have swallowed its declaration) is unverifiable, not missing.
    if node is not None or root.has_error:
        return SymbolLookup(status="parse_error", detail="syntax error")
    return SymbolLookup(status="missing")


def _find_ts_symbol(root: Node, symbol: str) -> Node | None:
    if "." in symbol:
        class_name, _, member = symbol.partition(".")
        for decl in _top_level_decls(root):
            if decl.type in _TS_CLASS_NODES and _node_name(decl) == class_name:
                return _find_method(decl, member)
        return None
    for decl in _top_level_decls(root):
        match = _match_named_decl(decl, symbol)
        if match is not None:
            return match
    return None


def _top_level_decls(root: Node) -> Iterator[Node]:
    """Yield top-level declarations, seeing through export/declare wrappers."""
    for child in root.named_children:
        yield from _unwrap(child)


def _unwrap(node: Node) -> Iterator[Node]:
    if node.type == _TS_EXPORT:
        inner = node.child_by_field_name("declaration") or node.child_by_field_name("value")
        if inner is not None:
            yield from _unwrap(inner)
        return
    if node.type == _TS_AMBIENT:
        for child in node.named_children:
            yield from _unwrap(child)
        return
    yield node


def _match_named_decl(decl: Node, symbol: str) -> Node | None:
    """Return the node declaring `symbol`, or None if this decl does not."""
    if decl.type in _TS_FUNCTION_NODES or decl.type in _TS_CLASS_NODES:
        return decl if _node_name(decl) == symbol else None
    if decl.type in _TS_BINDING_NODES:
        return _match_function_binding(decl, symbol)
    return None


def _match_function_binding(decl: Node, symbol: str) -> Node | None:
    """A const/let/var binding matches only when bound to a function/arrow."""
    for child in decl.named_children:
        if child.type != "variable_declarator":
            continue
        value = child.child_by_field_name("value")
        if (
            _node_name(child) == symbol
            and value is not None
            and value.type in _TS_FUNCTION_VALUES
        ):
            return child
    return None


def _find_method(class_node: Node, member: str) -> Node | None:
    body = class_node.child_by_field_name("body")
    if body is None:
        return None
    for child in body.named_children:
        if child.type in _TS_METHOD_NODES and _node_name(child) == member:
            return child
    return None


def _node_name(node: Node) -> str | None:
    name = node.child_by_field_name("name")
    return name.text.decode("utf-8") if name is not None and name.text is not None else None
