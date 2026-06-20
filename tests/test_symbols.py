"""The pure language seam: locate(source, path, symbol) -> SymbolLookup.

These exercise symbol resolution directly on source text, independent of the
filesystem. Language is inferred from the path extension only. tree-sitter is
error-recovering, so the JS/TS contract is "found-despite-error": a cleanly
parsed symbol resolves even when another part of the file is broken, but a name
that cannot be cleanly located in a file that failed to parse is unverifiable
(parse_error), never reported missing.
"""
from __future__ import annotations

from msv.symbols import ReexportEdge, SymbolLookup, locate

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


# --- Python Layer A: absent (missing/stale) vs present-but-indirect -----------


def test_py_data_binding_is_indirect_not_missing():
    # A module-level data binding is present, just not a callable -> indirect.
    res = locate("X = 5\n", "a.py", "X")
    assert res.status == "indirect"
    assert res.detail == "noncallable"


def test_py_reexport_is_indirect():
    res = locate("from .core import parse\n", "a.py", "parse")
    assert res.status == "indirect"
    assert res.detail == "reexport"


def test_py_wildcard_makes_absence_indirect():
    # A star-import may supply the name, so absence is not provable.
    res = locate("from x import *\n", "a.py", "mystery")
    assert res.status == "indirect"
    assert res.detail == "wildcard"


def test_py_module_getattr_is_indirect():
    # PEP 562 module __getattr__ can synthesize any name on access.
    src = "def __getattr__(name):\n    raise AttributeError(name)\n"
    res = locate(src, "a.py", "anything")
    assert res.status == "indirect"
    assert res.detail == "module_getattr"


def test_py_nested_def_is_indirect():
    src = "def outer():\n    def inner():\n        return 1\n    return inner\n"
    res = locate(src, "a.py", "inner")
    assert res.status == "indirect"
    assert res.detail == "nested"


def test_py_truly_absent_is_missing_stale():
    # Name bound nowhere in a clean file -> provably absent -> missing (stale).
    # Guards against over-suppression turning real deletions into unverifiable.
    assert locate("def f():\n    return 1\n", "a.py", "ghost").status == "missing"


def test_py_method_maybe_inherited_is_indirect():
    src = (
        "class Base:\n    def shared(self):\n        return 1\n\n"
        "class Sub(Base):\n    def own(self):\n        return 2\n"
    )
    assert locate(src, "a.py", "Sub.shared").status == "indirect"
    assert locate(src, "a.py", "Sub.shared").detail == "maybe_inherited"
    assert locate(src, "a.py", "Sub.own").status == "found"
    assert locate(src, "a.py", "Base.shared").status == "found"


def test_py_method_absent_no_base_is_missing():
    # No base class to inherit from, method absent -> provably missing (stale).
    src = "class C:\n    def m(self):\n        return 1\n"
    assert locate(src, "a.py", "C.ghost").status == "missing"


def test_py_method_on_indirect_class_is_indirect():
    # The class itself only arrives via re-export; we cannot resolve its method.
    res = locate("from .models import Widget\n", "a.py", "Widget.render")
    assert res.status == "indirect"


def test_python_symbol_none_is_file_presence():
    res = locate("x = 1\n", "a.py", None)
    assert res.status == "found"
    assert res.lineno == 1


def test_python_parse_error():
    assert locate("def f(:\n    pass\n", "a.py", "f").status == "parse_error"


def test_python_symbol_none_on_broken_file_is_parse_error():
    assert locate("def f(:\n", "a.py", None).status == "parse_error"


# --- Python Layer B: interface extraction on a found symbol -------------------


def test_py_interface_function_arity():
    iface = locate("def f(a, b, c=1):\n    return 1\n", "a.py", "f").interface
    assert iface is not None
    assert iface.category == "func"
    assert iface.req_positional == 2
    assert iface.max_positional == 3
    assert iface.has_star is False
    assert iface.has_kw is False


def test_py_interface_star_and_kwargs():
    iface = locate("def f(a, *args, **kw):\n    return 1\n", "a.py", "f").interface
    assert iface.req_positional == 1
    assert iface.max_positional == 1
    assert iface.has_star is True
    assert iface.has_kw is True


def test_py_interface_keyword_only_required():
    iface = locate("def f(a, *, b, c=1):\n    return 1\n", "a.py", "f").interface
    assert iface.req_kwonly == 1  # b required, c has a default


def test_py_interface_async_category():
    iface = locate("async def f():\n    return 1\n", "a.py", "f").interface
    assert iface.category == "async_func"


def test_py_interface_generator_flag():
    iface = locate("def g():\n    yield 1\n", "a.py", "g").interface
    assert iface.is_generator is True


def test_py_interface_generator_ignores_nested_yield():
    # A yield inside a nested function does not make the outer a generator.
    src = "def g():\n    def inner():\n        yield 1\n    return inner\n"
    iface = locate(src, "a.py", "g").interface
    assert iface.is_generator is False


def test_py_interface_class_base_count():
    iface = locate("class C(A, B):\n    pass\n", "a.py", "C").interface
    assert iface.category == "class"
    assert iface.base_count == 2


def test_py_interface_method_decorators():
    src = (
        "class C:\n"
        "    @staticmethod\n"
        "    def s():\n        return 1\n"
        "    @property\n"
        "    def p(self):\n        return 1\n"
    )
    assert locate(src, "a.py", "C.s").interface.contract_decorators == frozenset({"staticmethod"})
    assert locate(src, "a.py", "C.p").interface.contract_decorators == frozenset({"property"})


def test_py_overloaded_symbol_interface_is_none_but_found():
    # Two top-level defs with the same name: exists, but shape is ambiguous.
    src = "def dup(a):\n    return a\n\n\ndef dup(a, b):\n    return (a, b)\n"
    res = locate(src, "a.py", "dup")
    assert res.status == "found"
    assert res.interface is None


def test_py_interface_none_when_no_symbol_requested():
    assert locate("x = 1\n", "a.py", None).interface is None


# --- Python re-export edge: the followable one-hop binding --------------------
# A relative, named, non-shadowed import carries a ReexportEdge with precomputed
# repo-relative candidate paths; every other indirection leaves reexport None.


def test_py_relative_named_import_sets_reexport_edge():
    res = locate("from .core import parse\n", "pkg/api.py", "parse")
    assert res.status == "indirect"
    assert res.detail == "reexport"
    edge = res.reexport
    assert edge is not None
    assert edge.name == "parse"
    assert edge.module_candidates == ("pkg/core.py", "pkg/core/__init__.py")
    assert edge.submodule_candidates == ("pkg/core/parse.py", "pkg/core/parse/__init__.py")


def test_py_aliased_import_edge_uses_original_name():
    # `as p` rebinds locally; the name resolved in the target stays the original.
    res = locate("from .core import parse as p\n", "pkg/api.py", "p")
    assert res.status == "indirect"
    assert res.reexport is not None
    assert res.reexport.name == "parse"
    # The submodule guard also keys off the original (source) name.
    assert res.reexport.submodule_candidates == ("pkg/core/parse.py", "pkg/core/parse/__init__.py")


def test_py_candidate_paths_dotlevel():
    # `..core.sub` ascends one package from pkg/sub/ and walks core/sub.
    res = locate("from ..core.sub import thing\n", "pkg/sub/m.py", "thing")
    assert res.reexport is not None
    assert res.reexport.module_candidates == ("pkg/core/sub.py", "pkg/core/sub/__init__.py")


def test_py_absolute_import_no_edge():
    # An absolute specifier needs sys.path; it is never followed.
    res = locate("from pkg.core import parse\n", "pkg/api.py", "parse")
    assert res.status == "indirect"
    assert res.detail == "reexport"
    assert res.reexport is None


def test_py_dot_only_import_no_edge():
    # `from . import core` (module is None) names a package member, not a
    # followable named re-export of a symbol.
    res = locate("from . import core\n", "pkg/api.py", "core")
    assert res.status == "indirect"
    assert res.reexport is None


def test_py_locally_shadowed_import_no_edge():
    # A local rebinding shadows the import; following would fingerprint the
    # wrong value, so the edge is suppressed.
    res = locate("from .core import parse\nparse = _wrap(parse)\n", "pkg/api.py", "parse")
    assert res.status == "indirect"
    assert res.reexport is None


def test_py_wildcard_has_no_edge():
    res = locate("from .core import *\n", "pkg/api.py", "mystery")
    assert res.status == "indirect"
    assert res.detail == "wildcard"
    assert res.reexport is None


def test_py_nonfollowable_indirects_have_no_edge():
    # Every non-import indirection stays edge-free (guards against widening).
    for src, name in [
        ("X = 5\n", "X"),  # noncallable
        ("def outer():\n    def inner():\n        return 1\n", "inner"),  # nested
        ("def __getattr__(n):\n    raise AttributeError(n)\n", "anything"),  # module_getattr
        ("__all__ = ['ghost']\n", "ghost"),  # __all__ re-export, no module edge
    ]:
        res = locate(src, "a.py", name)
        assert res.status == "indirect"
        assert res.reexport is None


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


# --- TypeScript: present-but-not-callable -> indirect (unverifiable) -----------
# These declarations are not resolvable callables, but the name IS bound, so its
# presence is not provable absence -> indirect, never stale.


def test_ts_data_const_is_indirect():
    res = locate("export const MAX = 5;\n", "a.ts", "MAX")
    assert res.status == "indirect"
    assert res.detail == "noncallable"


def test_ts_interface_is_indirect():
    res = locate("export interface User {}\n", "a.ts", "User")
    assert res.status == "indirect"
    assert res.detail == "noncallable"


def test_ts_type_alias_is_indirect():
    res = locate("export type Id = string;\n", "a.ts", "Id")
    assert res.status == "indirect"
    assert res.detail == "noncallable"


def test_ts_enum_is_indirect():
    res = locate("export enum Role { A, B }\n", "a.ts", "Role")
    assert res.status == "indirect"
    assert res.detail == "noncallable"


def test_ts_const_interface_type_enum_are_indirect():
    # The sanctioned contract change: every value/type-only declaration form is
    # present-but-indirect rather than missing.
    for src, name in [
        ("const MAX = 5;\n", "MAX"),
        ("interface User {}\n", "User"),
        ("type Id = string;\n", "Id"),
        ("enum Role { A, B }\n", "Role"),
    ]:
        assert locate(src, "a.ts", name).status == "indirect"


# --- TypeScript: re-export / barrel / commonjs / nested -> indirect ------------


def test_ts_named_import_is_indirect():
    res = locate("import { parse } from './core';\n", "a.ts", "parse")
    assert res.status == "indirect"
    assert res.detail == "reexport"


def test_ts_named_reexport_is_indirect():
    res = locate("export { parse } from './core';\n", "a.ts", "parse")
    assert res.status == "indirect"
    assert res.detail == "reexport"


def test_ts_aliased_reexport_is_indirect():
    # Both the original and the alias are treated as re-exported (conservative).
    src = "export { orig as parse } from './core';\n"
    assert locate(src, "a.ts", "parse").status == "indirect"
    assert locate(src, "a.ts", "orig").status == "indirect"


def test_ts_barrel_star_is_indirect():
    # `export * from` may supply any name, so an absent name is unverifiable.
    res = locate("export * from './core';\n", "a.ts", "mystery")
    assert res.status == "indirect"
    assert res.detail == "wildcard"


def test_ts_namespace_reexport_binds_name_is_indirect():
    res = locate("export * as ns from './core';\n", "a.ts", "ns")
    assert res.status == "indirect"
    assert res.detail == "reexport"


def test_ts_nested_function_is_indirect():
    src = "function outer() {\n  function inner() {}\n  return inner;\n}\n"
    res = locate(src, "a.ts", "inner")
    assert res.status == "indirect"
    assert res.detail == "nested"


def test_js_commonjs_module_exports_is_indirect():
    res = locate("module.exports = { foo() {} };\n", "a.js", "foo")
    assert res.status == "indirect"
    assert res.detail == "commonjs_dynamic"


def test_js_commonjs_exports_member_is_indirect():
    res = locate("exports.foo = function () {};\n", "a.js", "foo")
    assert res.status == "indirect"
    assert res.detail == "commonjs_dynamic"


# --- TypeScript: provable absence stays missing (stale); recall guard ----------


def test_ts_unknown_name_in_clean_file_is_missing():
    assert locate("function a() {}\n", "a.ts", "b").status == "missing"


def test_ts_missing_method_on_existing_class_no_heritage_is_missing():
    assert locate("class C {\n  m() {}\n}\n", "a.ts", "C.nope").status == "missing"


def test_ts_method_on_missing_class_is_missing():
    assert locate("class C {}\n", "a.ts", "Ghost.m").status == "missing"


def test_ts_method_maybe_inherited_is_indirect():
    src = "class Sub extends Base {\n  own() {}\n}\n"
    res = locate(src, "a.ts", "Sub.shared")
    assert res.status == "indirect"
    assert res.detail == "maybe_inherited"


def test_ts_method_implements_is_maybe_inherited():
    # `implements` counts as heritage: declaration-merging/mixins could supply it.
    src = "class C implements I {\n  m() {}\n}\n"
    assert locate(src, "a.ts", "C.other").status == "indirect"


# --- TypeScript Layer B: interface extraction ---------------------------------


def test_ts_interface_function_arity():
    # a required; b? optional; c has a default -> 1 required of 3 positional.
    iface = locate("function f(a: number, b?: string, c = 1) {}\n", "a.ts", "f").interface
    assert iface is not None
    assert iface.category == "func"
    assert iface.req_positional == 1
    assert iface.max_positional == 3
    assert iface.has_star is False


def test_ts_interface_rest_param():
    iface = locate("function f(a, ...rest) {}\n", "a.ts", "f").interface
    assert iface.req_positional == 1
    assert iface.max_positional == 1
    assert iface.has_star is True


def test_ts_interface_async_category():
    assert locate("async function f() {}\n", "a.ts", "f").interface.category == "async_func"


def test_ts_interface_async_arrow_const():
    assert locate("const f = async (a) => a;\n", "a.ts", "f").interface.category == "async_func"


def test_ts_interface_generator_flag():
    assert locate("function* g() {}\n", "a.ts", "g").interface.is_generator is True


def test_ts_interface_arrow_const_arity():
    iface = locate("const f = (a, b = 1) => a;\n", "a.ts", "f").interface
    assert iface.req_positional == 1
    assert iface.max_positional == 2


def test_ts_interface_parenless_arrow_single_param():
    # `x => x` has no formal_parameters node but is one required parameter.
    iface = locate("const f = x => x;\n", "a.ts", "f").interface
    assert iface.req_positional == 1
    assert iface.max_positional == 1


def test_ts_interface_method_static_and_getter_decorators():
    src = "class C {\n  static s() {}\n  get x() { return 1; }\n}\n"
    assert locate(src, "a.ts", "C.s").interface.contract_decorators == frozenset({"static"})
    assert locate(src, "a.ts", "C.x").interface.contract_decorators == frozenset({"getter"})


def test_ts_interface_class_base_count_extends_and_implements():
    iface = locate("class C extends B implements I, J {}\n", "a.ts", "C").interface
    assert iface.category == "class"
    assert iface.base_count == 3


def test_ts_overloaded_function_interface_is_none_but_found():
    src = (
        "function f(a: number): number;\n"
        "function f(a: string): string;\n"
        "function f(a: any): any { return a; }\n"
    )
    res = locate(src, "a.ts", "f")
    assert res.status == "found"
    assert res.interface is None


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


def test_dts_ambient_typed_const_is_indirect():
    # `declare const X: number` has no function value, but the name is bound, so
    # it is present-but-indirect rather than provably absent.
    res = locate("declare const X: number;\n", "x.d.ts", "X")
    assert res.status == "indirect"
    assert res.detail == "noncallable"


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
