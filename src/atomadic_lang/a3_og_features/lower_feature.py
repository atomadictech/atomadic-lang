"""Tier a3 — orchestrate file/package lowering.

Walks a tier-organized Python package, applies the a1 helpers per file,
and assembles the full .atm module text. Computes density measurements.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..a0_qk_constants.atm_grammar import (
    DROPPED_TOP_LEVEL,
    TIER_DIRS,
)
from ..a0_qk_constants.atm_types import (
    LoweredDecl,
    LoweredModule,
    LoweredParam,
)
from ..a1_at_functions.atm_emit import count_atm_tokens, count_py_tokens, emit_module
from ..a1_at_functions.body_to_atm import lower_function_body
from ..a1_at_functions.tier_infer import (
    effect_for_tier,
    package_from_path,
    tier_from_path,
)
from ..a1_at_functions.type_to_sigil import annotation_to_sigil


def lower_file(py_path: Path, package: str | None = None) -> tuple[list[LoweredDecl], int]:
    """Lower a single Python file. Returns (decls, py_token_count).

    Decls are top-level function definitions only in v0. Module docstrings
    and imports are dropped (info preserved by tier sigil + tier-organized
    layout). Class declarations are deferred to v0.5.
    """
    py_path = Path(py_path).resolve()
    source = py_path.read_text(encoding="utf-8")
    py_tokens = count_py_tokens(source)

    tier = tier_from_path(py_path)
    effect = effect_for_tier(tier)
    rel_path = _relative_to_package(py_path, package)

    tree = ast.parse(source, filename=str(py_path))
    decls: list[LoweredDecl] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in DROPPED_TOP_LEVEL:
                continue
            decls.append(_lower_function(node, tier, effect, rel_path))
        elif isinstance(node, ast.ClassDef):
            # v0.7: lower classes to a flat list of {field-decl, method-decls}.
            decls.extend(_lower_class(node, tier, effect, rel_path))
        # Module-level constants: x: int = 5 / x = 5
        elif isinstance(node, ast.AnnAssign) and tier == 0:
            decls.append(_lower_const_assign(node, tier, rel_path))
        elif isinstance(node, ast.Assign) and tier == 0:
            for d in _lower_plain_assign(node, tier, rel_path):
                decls.append(d)
        # Imports, docstrings — drop.

    return decls, py_tokens


def lower_package(pkg_root: Path) -> LoweredModule:
    """Lower an entire tier-organized Python package.

    `pkg_root` should point at the directory containing the ``aN_*`` tier
    subdirectories — e.g. ``forge-demo-calc/src/calc``.

    Returns a LoweredModule with combined decls and density metrics.
    """
    pkg_root = Path(pkg_root).resolve()
    if not pkg_root.is_dir():
        raise ValueError(f"package root does not exist or is not a directory: {pkg_root}")

    package = pkg_root.name
    all_decls: list[LoweredDecl] = []
    py_total = 0

    # Walk every aN_* tier directory in order.
    # Real-world corpora include in-progress files with SyntaxError, encoding
    # quirks, or partially-broken type annotations. Skip those at the
    # package level rather than aborting the whole walk; ``lower_file`` itself
    # remains strict for callers that want fail-fast semantics.
    for tier_name in TIER_DIRS:
        tier_dir = pkg_root / tier_name
        if not tier_dir.is_dir():
            continue
        for py_file in sorted(tier_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                decls, py_tokens = lower_file(py_file, package=package)
            except (SyntaxError, UnicodeDecodeError, ValueError):
                # Skip unparseable / undecodable files; the package-level
                # corpus is best-effort over real source trees.
                continue
            all_decls.extend(decls)
            py_total += py_tokens

    atm_text = emit_module(package, all_decls)
    atm_tokens = count_atm_tokens(atm_text)
    density = (py_total / atm_tokens) if atm_tokens > 0 else 0.0

    return LoweredModule(
        schema_version="atomadic-lang.lower/v0",
        package=package,
        decls=all_decls,
        py_token_count=py_total,
        atm_token_count=atm_tokens,
        density_ratio=density,
    )


# Dunder methods we drop from class lowering (info preserved structurally
# elsewhere or deemed boilerplate for v0.7).
_CLASS_DUNDER_DROP: frozenset[str] = frozenset({
    "__repr__", "__str__", "__hash__", "__eq__", "__ne__", "__lt__",
    "__le__", "__gt__", "__ge__", "__bool__", "__contains__",
    "__len__", "__iter__", "__next__", "__enter__", "__exit__",
})


def _lower_class(
    node: ast.ClassDef,
    tier: int,
    effect: str,
    source_path: str,
) -> list[LoweredDecl]:
    """Lower a Python class to a flat list of declarations.

    Emits:
    - one ``class`` form decl listing the inferred fields, e.g. ``2σ Counter ⟨value:i⟩``
    - one decl per non-dunder method, e.g. ``2σ Counter.increment ⟨self:Counter⟩→∅ = …``

    `__init__` is consumed for field inference; not emitted as a method.
    Dunders (``__repr__``, ``__str__``, etc.) are dropped per v0.7 scope.
    Inheritance, decorators, and class-level attrs other than fields are deferred.
    """
    decls: list[LoweredDecl] = []
    fields = _infer_class_fields(node)

    # Field declaration (the class itself).
    decls.append(LoweredDecl(
        tier=tier,                          # type: ignore[typeddict-item]
        effect=effect,                       # type: ignore[typeddict-item]
        name=node.name,
        params=fields,
        return_sigil="",
        body_form="class",                   # type: ignore[typeddict-item]
        body="",
        pre="",
        post="",
        source_path=source_path,
        source_lineno=node.lineno,
    ))

    # Methods.
    for stmt in node.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if stmt.name == "__init__":
            continue  # consumed for field inference
        if stmt.name in _CLASS_DUNDER_DROP:
            continue
        decls.append(_lower_method(stmt, node.name, tier, effect, source_path))

    return decls


def _infer_class_fields(node: ast.ClassDef) -> list[LoweredParam]:
    """Infer the field list of a class.

    Sources, in priority:
    1. Class-body ``AnnAssign`` (TypedDict / dataclass-style ``field: type``)
    2. ``__init__`` body's ``self.x = expr`` and ``self.x: type = expr`` patterns
       — type inferred from the constructor's arg annotation when ``self.x = arg``
       or from the literal value type when ``self.x = 5``.
    """
    fields: list[LoweredParam] = []
    seen: set[str] = set()

    # 1. class-body annotations
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            if name in seen:
                continue
            seen.add(name)
            fields.append(LoweredParam(
                name=name,
                type_sigil=annotation_to_sigil(stmt.annotation),
            ))

    # 2. __init__-derived fields
    init = next(
        (s for s in node.body
         if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == "__init__"),
        None,
    )
    if init is not None:
        # Map of arg-name → annotation sigil (used when self.x = arg)
        arg_types: dict[str, str] = {}
        for arg in init.args.args[1:]:  # skip self
            arg_types[arg.arg] = annotation_to_sigil(arg.annotation)

        for stmt in init.body:
            # self.x = expr
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    fname = target.attr
                    if fname in seen:
                        continue
                    seen.add(fname)
                    fields.append(LoweredParam(
                        name=fname,
                        type_sigil=_infer_value_sigil(stmt.value, arg_types),
                    ))
            # self.x: T = expr
            elif isinstance(stmt, ast.AnnAssign):
                target = stmt.target
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    fname = target.attr
                    if fname in seen:
                        continue
                    seen.add(fname)
                    fields.append(LoweredParam(
                        name=fname,
                        type_sigil=annotation_to_sigil(stmt.annotation),
                    ))

    return fields


def _infer_value_sigil(value: ast.expr, arg_types: dict[str, str]) -> str:
    """Best-effort type sigil for a self.x = <value> RHS."""
    # self.x = <some_arg>  → use the constructor arg's annotation
    if isinstance(value, ast.Name) and value.id in arg_types:
        return arg_types[value.id]
    # Literal constants: 0 → i, 0.0 → f, "" → s, True → b, None → ∅
    if isinstance(value, ast.Constant):
        v = value.value
        if isinstance(v, bool):
            return "b"
        if isinstance(v, int):
            return "i"
        if isinstance(v, float):
            return "f"
        if isinstance(v, str):
            return "s"
        if v is None:
            return "∅"
    # Empty containers: [] → [_], {} → {_:_}
    if isinstance(value, ast.List):
        return "[_]"
    if isinstance(value, ast.Dict):
        return "{_:_}"
    if isinstance(value, ast.Tuple):
        return "(_)"
    return "_"


def _lower_method(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    class_name: str,
    tier: int,
    effect: str,
    source_path: str,
) -> LoweredDecl:
    """Lower a class method as ``ClassName.method_name`` declaration.

    The first arg (``self``/``cls``) is typed as the class name itself —
    it shows up in the param list as ``self:ClassName``.
    """
    params: list[LoweredParam] = []
    for i, arg in enumerate(method.args.args):
        if i == 0 and arg.arg in ("self", "cls"):
            params.append(LoweredParam(name=arg.arg, type_sigil=class_name))
        else:
            params.append(LoweredParam(
                name=arg.arg,
                type_sigil=annotation_to_sigil(arg.annotation),
            ))
    return_sigil = annotation_to_sigil(method.returns)
    body = lower_function_body(method.body)
    return LoweredDecl(
        tier=tier,                          # type: ignore[typeddict-item]
        effect=effect,                       # type: ignore[typeddict-item]
        name=f"{class_name}.{method.name}",
        params=params,
        return_sigil=return_sigil,
        body_form=body.form,                 # type: ignore[typeddict-item]
        body=body.body,
        pre=body.pre,
        post=body.post,
        source_path=source_path,
        source_lineno=method.lineno,
    )


def _lower_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    tier: int,
    effect: str,
    source_path: str,
) -> LoweredDecl:
    """Lower a Python function-def AST node to a LoweredDecl."""
    params: list[LoweredParam] = [
        LoweredParam(name=arg.arg, type_sigil=annotation_to_sigil(arg.annotation))
        for arg in node.args.args
    ]
    return_sigil = annotation_to_sigil(node.returns)
    body = lower_function_body(node.body)
    return LoweredDecl(
        tier=tier,                          # type: ignore[typeddict-item]
        effect=effect,                       # type: ignore[typeddict-item]
        name=node.name,
        params=params,
        return_sigil=return_sigil,
        body_form=body.form,                 # type: ignore[typeddict-item]
        body=body.body,
        pre=body.pre,
        post=body.post,
        source_path=source_path,
        source_lineno=node.lineno,
    )


def _lower_const_assign(node: ast.AnnAssign, tier: int, source_path: str) -> LoweredDecl:
    """Lower a tier-0 ``x: T = value`` annotated assignment."""
    name = node.target.id if isinstance(node.target, ast.Name) else "_"
    type_sigil = annotation_to_sigil(node.annotation)
    body = "_"
    if node.value is not None:
        from ..a1_at_functions.body_to_atm import lower_expr
        body = lower_expr(node.value)
    return LoweredDecl(
        tier=tier,                          # type: ignore[typeddict-item]
        effect="",                           # type: ignore[typeddict-item]
        name=name,
        params=[],
        return_sigil=type_sigil,
        body_form="inline",                  # type: ignore[typeddict-item]
        body=body,
        pre="",
        post="",
        source_path=source_path,
        source_lineno=node.lineno,
    )


def _lower_plain_assign(node: ast.Assign, tier: int, source_path: str) -> list[LoweredDecl]:
    """Lower tier-0 ``x = value`` (un-annotated) assignments."""
    out: list[LoweredDecl] = []
    from ..a1_at_functions.body_to_atm import lower_expr
    rhs = lower_expr(node.value) if node.value is not None else "_"
    for target in node.targets:
        if isinstance(target, ast.Name):
            out.append(LoweredDecl(
                tier=tier,                  # type: ignore[typeddict-item]
                effect="",                   # type: ignore[typeddict-item]
                name=target.id,
                params=[],
                return_sigil="_",
                body_form="inline",          # type: ignore[typeddict-item]
                body=rhs,
                pre="",
                post="",
                source_path=source_path,
                source_lineno=node.lineno,
            ))
    return out


def _relative_to_package(py_path: Path, package: str | None) -> str:
    """Render a relative path string for traceability fields.

    Best-effort: returns the full path if the package boundary cannot be
    located. Lowering is total — it never raises here.
    """
    try:
        if package is None:
            package = package_from_path(py_path)
        parts = py_path.parts
        for i, part in enumerate(parts):
            if part == package:
                return "/".join(parts[i:])
        return py_path.name
    except Exception:
        return py_path.name
