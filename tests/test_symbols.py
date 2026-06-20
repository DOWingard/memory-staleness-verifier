"""The pure language seam: locate(source, path, symbol) -> SymbolLookup.

These exercise symbol resolution directly on source text, independent of the
filesystem. Language is inferred from the path extension only. tree-sitter is
error-recovering, so the JS/TS contract is "found-despite-error": a cleanly
parsed symbol resolves even when another part of the file is broken, but a name
that cannot be cleanly located in a file that failed to parse is unverifiable
(parse_error), never reported missing.
"""
from __future__ import annotations

from msv.symbols import SymbolLookup, locate

# --- Python parity (logic moved out of resolution.py) ------------------------


def test_python_function_found():
    res = locate("def f():\n    return 1\n", "a.py", "f")
    assert res.status == "found"
    assert res.lineno == 1


def test_python_class_and_method_found():
    src = "class C:\n    def m(self):\n        return 1\n"
    assert locate(src, "a.py", "C").status == "found"
    method = locate(src, "a.py", "C.m")
    assert method.status == "found"
    assert method.lineno == 2


def test_python_missing_symbol_in_clean_file():
    assert locate("def f():\n    pass\n", "a.py", "ghost").status == "missing"


def test_python_symbol_none_is_file_presence():
    res = locate("x = 1\n", "a.py", None)
    assert res.status == "found"
    assert res.lineno == 1


def test_python_parse_error():
    assert locate("def f(:\n    pass\n", "a.py", "f").status == "parse_error"


def test_python_symbol_none_on_broken_file_is_parse_error():
    assert locate("def f(:\n", "a.py", None).status == "parse_error"


# --- TypeScript: the recognized declaration forms ----------------------------


def test_ts_function_declaration_found():
    res = locate("function refresh() {\n  return 1;\n}\n", "a.ts", "refresh")
    assert res.status == "found"
    assert res.lineno == 1


def test_ts_async_function_found():
    assert locate("async function revoke() {}\n", "a.ts", "revoke").status == "found"


def test_ts_generator_function_found():
    assert locate("function* gen() {}\n", "a.ts", "gen").status == "found"


def test_ts_class_found():
    assert locate("class Svc {\n  login() {}\n}\n", "a.ts", "Svc").status == "found"


def test_ts_abstract_class_found():
    assert locate("abstract class Base {}\n", "a.ts", "Base").status == "found"


def test_ts_method_found_with_lineno():
    src = "class Svc {\n  login() {}\n  static make() {}\n  get url() { return ''; }\n}\n"
    assert locate(src, "a.ts", "Svc.login").lineno == 2
    assert locate(src, "a.ts", "Svc.make").status == "found"  # static
    assert locate(src, "a.ts", "Svc.url").status == "found"  # getter


def test_ts_arrow_const_found():
    res = locate("const handler = () => {};\n", "a.ts", "handler")
    assert res.status == "found"
    assert res.lineno == 1


def test_ts_function_expression_const_found():
    assert locate("const h = function () {};\n", "a.ts", "h").status == "found"


def test_ts_exported_function_found():
    assert locate("export function e() {}\n", "a.ts", "e").status == "found"


def test_ts_default_exported_named_function_found():
    assert locate("export default function d() {}\n", "a.ts", "d").status == "found"


def test_ts_exported_arrow_const_found():
    assert locate("export const Comp = () => {};\n", "a.ts", "Comp").status == "found"


# --- TypeScript: Mirror-Python exclusions (=> missing => stale) ---------------


def test_ts_data_const_is_missing():
    assert locate("export const MAX = 5;\n", "a.ts", "MAX").status == "missing"


def test_ts_interface_is_missing():
    assert locate("export interface User {}\n", "a.ts", "User").status == "missing"


def test_ts_type_alias_is_missing():
    assert locate("export type Id = string;\n", "a.ts", "Id").status == "missing"


def test_ts_enum_is_missing():
    assert locate("export enum Role { A, B }\n", "a.ts", "Role").status == "missing"


def test_ts_unknown_name_in_clean_file_is_missing():
    assert locate("function a() {}\n", "a.ts", "b").status == "missing"


def test_ts_missing_method_on_existing_class_is_missing():
    assert locate("class C {\n  m() {}\n}\n", "a.ts", "C.nope").status == "missing"


def test_ts_method_on_missing_class_is_missing():
    assert locate("class C {}\n", "a.ts", "Ghost.m").status == "missing"


# --- TypeScript: found-despite-error -----------------------------------------

_BROKEN = "function good() {\n  return 1;\n}\nfunction bad( {\nfunction alsoGood() {}\n"


def test_ts_clean_symbol_found_despite_error_elsewhere():
    # `good` parses cleanly before the broken `bad`; it must still resolve.
    res = locate(_BROKEN, "a.ts", "good")
    assert res.status == "found"
    assert res.lineno == 1


def test_ts_symbol_in_error_region_is_parse_error_not_missing():
    # `bad` was swallowed by the parse error; we must not claim it is missing.
    assert locate(_BROKEN, "a.ts", "bad").status == "parse_error"


def test_ts_absent_name_in_broken_file_is_parse_error_not_missing():
    # The error may have eaten the declaration, so absence is unverifiable.
    assert locate(_BROKEN, "a.ts", "totally_absent").status == "parse_error"


def test_ts_symbol_none_on_broken_file_is_parse_error():
    assert locate(_BROKEN, "a.ts", None).status == "parse_error"


def test_ts_symbol_none_on_clean_file_is_found():
    res = locate("function a() {}\n", "a.ts", None)
    assert res.status == "found"
    assert res.lineno == 1


# --- TSX / JSX ----------------------------------------------------------------


def test_tsx_component_arrow_const_found():
    src = "export const Button = (props) => {\n  return <div>{props.x}</div>;\n};\n"
    assert locate(src, "Button.tsx", "Button").status == "found"


def test_tsx_default_function_component_found():
    src = "export default function App() {\n  return <div/>;\n}\n"
    assert locate(src, "App.tsx", "App").status == "found"


def test_jsx_component_found():
    src = "export function Card() {\n  return <div/>;\n}\n"
    assert locate(src, "Card.jsx", "Card").status == "found"


# --- JavaScript flavors (extension -> grammar mapping) ------------------------


def test_js_function_and_arrow_and_method():
    src = "function a() {}\nconst b = () => {};\nclass C {\n  m() {}\n}\n"
    assert locate(src, "x.js", "a").status == "found"
    assert locate(src, "x.js", "b").status == "found"
    assert locate(src, "x.js", "C.m").status == "found"


def test_mjs_extension_resolves():
    assert locate("export const f = () => {};\n", "x.mjs", "f").status == "found"


def test_cjs_extension_resolves():
    assert locate("function f() {}\n", "x.cjs", "f").status == "found"


# --- .d.ts ambient declarations ----------------------------------------------


def test_dts_ambient_function_found():
    assert locate("declare function refresh(): void;\n", "x.d.ts", "refresh").status == "found"


def test_dts_ambient_class_and_method_found():
    src = "declare class Svc {\n  login(): void;\n}\n"
    assert locate(src, "x.d.ts", "Svc").status == "found"
    assert locate(src, "x.d.ts", "Svc.login").status == "found"


def test_dts_export_declare_function_found():
    assert locate("export declare function e(): void;\n", "x.d.ts", "e").status == "found"


def test_dts_ambient_typed_const_is_missing():
    # `declare const X: number` has no function value -> Mirror-Python excludes it.
    assert locate("declare const X: number;\n", "x.d.ts", "X").status == "missing"


# --- Unsupported languages ----------------------------------------------------


def test_unsupported_extension_go():
    assert locate("func Foo() {}\n", "main.go", "Foo").status == "unsupported"


def test_unsupported_extension_markdown():
    assert locate("# title\n", "README.md", None).status == "unsupported"


def test_unsupported_no_extension():
    assert locate("all:\n\techo hi\n", "Makefile", None).status == "unsupported"


def test_unsupported_short_circuits_before_parse():
    # An unsupported file is reported unsupported regardless of a requested symbol.
    assert locate("anything at all", "x.rb", "Foo").status == "unsupported"


# --- Contract shape -----------------------------------------------------------


def test_lookup_is_frozen():
    res = locate("def f(): pass\n", "a.py", "f")
    assert isinstance(res, SymbolLookup)
    try:
        res.status = "missing"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("SymbolLookup should be immutable")
