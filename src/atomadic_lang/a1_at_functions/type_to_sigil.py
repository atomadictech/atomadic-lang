"""Tier a1 — pure mapping from Python ast type annotations to .atm type sigils.

Handles the v0 subset: int, float, str, bool, list[T], dict[K,V], Optional[T], None.
Unknown / un-annotated types lower to ``"_"``.
"""

from __future__ import annotations

import ast

from ..a0_qk_constants.atm_grammar import PY_TYPE_TO_SIGIL


def annotation_to_sigil(node: ast.AST | None) -> str:
    """Convert a Python type-annotation AST node to an .atm type sigil.

    Returns ``"_"`` for missing or unrecognised annotations.
    """
    if node is None:
        return "_"

    # Bare names: int, float, str, bool, None, Any, …
    if isinstance(node, ast.Name):
        return PY_TYPE_TO_SIGIL.get(node.id, "_")

    # ``None`` literal as an annotation (Python 3.10+ allows this).
    if isinstance(node, ast.Constant) and node.value is None:
        return "∅"

    # Subscripted: list[int], dict[str, int], Optional[int], tuple[...], etc.
    # v2.6 fix (per swarm code-critic): dispatch on the actual base name, not
    # on the recursively-lowered sigil. Previously `tuple[int,str]` and
    # `Mapping[K,V]` both lowered to `[_]` because `base in ("list","List","_")`
    # matched the fallback "_" sigil for unknown bases.
    if isinstance(node, ast.Subscript):
        slice_node = node.slice
        base_name: str | None = None
        if isinstance(node.value, ast.Name):
            base_name = node.value.id
        elif isinstance(node.value, ast.Attribute):
            base_name = node.value.attr  # typing.List → List

        # list[T], List[T], Sequence[T], Iterable[T] → [T]
        if base_name in ("list", "List", "Sequence", "Iterable"):
            return f"[{annotation_to_sigil(slice_node)}]"

        # dict[K, V], Dict[K, V], Mapping[K, V] → {K:V}
        if base_name in ("dict", "Dict", "Mapping", "MutableMapping"):
            if isinstance(slice_node, ast.Tuple) and len(slice_node.elts) == 2:
                k = annotation_to_sigil(slice_node.elts[0])
                v = annotation_to_sigil(slice_node.elts[1])
                return f"{{{k}:{v}}}"
            return "{_:_}"

        # Optional[T] → ?T
        if base_name == "Optional":
            return f"?{annotation_to_sigil(slice_node)}"

        # tuple[A, B, C] → (A,B,C)  — v2.6 added explicitly
        if base_name in ("tuple", "Tuple"):
            if isinstance(slice_node, ast.Tuple):
                inner = ",".join(annotation_to_sigil(e) for e in slice_node.elts)
                return f"({inner})"
            return f"({annotation_to_sigil(slice_node)})"

        # Set[T], FrozenSet[T] — preserved as set literal
        if base_name in ("set", "Set", "frozenset", "FrozenSet"):
            return f"{{{annotation_to_sigil(slice_node)}}}"

        # Union[A, B, ...] → ?_-ish; for v2.6 just use the first arm with a "?"
        # prefix to mark uncertainty.
        if base_name == "Union":
            if isinstance(slice_node, ast.Tuple) and slice_node.elts:
                first = annotation_to_sigil(slice_node.elts[0])
                return f"?{first}"
            return "?_"

        # Unknown subscript shape — return underscore (NOT the fallback list).
        return "_"

    # Attribute (typing.List etc) — strip qualifier.
    if isinstance(node, ast.Attribute):
        return PY_TYPE_TO_SIGIL.get(node.attr, "_")

    return "_"


def list_sigil(inner: str) -> str:
    """Construct the .atm sigil for a list of `inner`."""
    return f"[{inner}]"


def map_sigil(key: str, value: str) -> str:
    """Construct the .atm sigil for a map from key to value."""
    return f"{{{key}:{value}}}"


def optional_sigil(inner: str) -> str:
    """Construct the .atm sigil for an optional `inner`."""
    return f"?{inner}"
