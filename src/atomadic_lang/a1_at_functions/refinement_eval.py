"""Tier a1 — pure refinement-predicate evaluator (decidable fragment, v2.0+v2.6).

Evaluates predicates from the v0 decidable fragment specified in
REFINED_DESIGN.md §4: QF-LIA ∪ QF-BV-finite-domain ∪ length-predicates ∪
enum-membership.

v2.6 (per swarm code-critic): replaced the ``eval()`` sandbox with an
AST-walk evaluator. The previous version was trivially exploitable —
``x.upper()`` and ``x.pop()`` passed the ``__/;/import`` filter and
called arbitrary attributes on bound objects. The AST-walk evaluator
allows only an explicit whitelist of node kinds and operators.

Imports nothing tier-internal beyond the stdlib.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from typing import Any


# A predicate is compiled to a Python callable taking a binding dict.
# Compilation runs once per refinement clause (paid at parse time);
# evaluation runs at every constrained-decoding token boundary.

CompiledPredicate = Callable[[dict[str, Any]], bool]


# Whitelisted operators. Any AST node kind not handled here is rejected.
_BINOP_FN: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_CMP_FN: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

_ALLOWED_NAMES: dict[str, Any] = {
    "true": True,
    "True": True,
    "false": False,
    "False": False,
    "None": None,
}

_ALLOWED_FUNCTIONS: dict[str, Callable] = {
    "len": len,
    "abs": abs,
    "min": min,
    "max": max,
}


class RefinementSyntaxError(ValueError):
    """Raised when a refinement predicate uses non-whitelisted syntax."""


def compile_predicate(text: str) -> CompiledPredicate:
    """Compile a refinement predicate text to a safe AST-walking callable.

    Supports (whitelist):
      - comparisons:  ``a≠b``, ``a≟b``, ``a≤b``, ``a≥b``, ``a<b``, ``a>b``
      - arithmetic:   ``+``, ``-``, ``*``, ``/``, ``//``, ``%``
      - length pred:  ``|xs|>0`` (treats ``|name|`` as ``len(name)``)
      - enum:         ``op∈{+,-,*,/}``
      - bool combine: ``∧`` (and), ``∨`` (or), ``¬`` (not)
      - constants:    integer / float literals, ``true`` / ``false``
      - whitelisted calls: ``len``, ``abs``, ``min``, ``max``

    NOT supported (rejected at compile time):
      - attribute access ``x.foo``
      - subscript ``x[i]``
      - any function call other than the whitelist
      - lambda, comprehensions, generator expressions
      - imports, exec, eval, anything reflective

    Returns a callable taking a binding dict ``{name: value}`` returning
    bool. Raises ``RefinementSyntaxError`` for non-whitelisted syntax.
    """
    py_text = _atm_to_python_syntax(text)
    try:
        tree = ast.parse(py_text, mode="eval")
    except SyntaxError as e:
        raise RefinementSyntaxError(f"could not parse refinement: {text!r}: {e}") from e

    # Validate the entire tree before compiling — reject anything not on the
    # whitelist. This is a static check, runs once at compile time.
    _validate_refinement_ast(tree.body, original=text)

    root = tree.body

    def _eval(bindings: dict[str, Any]) -> bool:
        return bool(_eval_node(root, bindings))

    return _eval


def _atm_to_python_syntax(text: str) -> str:
    """Translate .atm-Unicode predicate operators to Python equivalents."""
    py_text = (
        text.replace("≟", "==")
            .replace("≠", "!=")
            .replace("≤", "<=")
            .replace("≥", ">=")
            .replace("∧", " and ")
            .replace("∨", " or ")
            .replace("¬", " not ")
    )
    # |xs| → len(xs)  (only handles the simple identifier case)
    py_text = re.sub(r"\|([A-Za-z_]\w*)\|", r"len(\1)", py_text)
    # x∈{a,b,c} → x in (a,b,c)
    py_text = re.sub(r"∈\{([^}]*)\}", r" in (\1,)", py_text)
    py_text = py_text.replace("∈", " in ")
    py_text = py_text.replace("∉", " not in ")
    return py_text


def _validate_refinement_ast(node: ast.AST, *, original: str) -> None:
    """Reject any node kind not on the refinement whitelist."""
    allowed_calls = set(_ALLOWED_FUNCTIONS.keys())
    for child in ast.walk(node):
        if isinstance(child, ast.expr_context):
            continue  # ast.Load / ast.Store / etc., fine
        # Reject every non-whitelisted node kind explicitly.
        if isinstance(child, (
            ast.Attribute, ast.Subscript, ast.Lambda,
            ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
            ast.Yield, ast.YieldFrom, ast.Await, ast.Starred,
            ast.IfExp,  # ternaries not in the v0 fragment
            ast.JoinedStr, ast.FormattedValue,  # no f-strings in refinements
        )):
            raise RefinementSyntaxError(
                f"refinement predicate uses unsupported syntax {type(child).__name__!r}: {original!r}"
            )
        if isinstance(child, ast.Call):
            # Only whitelisted function names; only positional args; no **kwargs.
            if not isinstance(child.func, ast.Name) or child.func.id not in allowed_calls:
                raise RefinementSyntaxError(
                    f"refinement predicate calls non-whitelisted function: {original!r}"
                )
            if any(isinstance(a, ast.Starred) for a in child.args) or child.keywords:
                raise RefinementSyntaxError(
                    f"refinement predicate uses *args / **kwargs: {original!r}"
                )


def _eval_node(node: ast.AST, bindings: dict[str, Any]) -> Any:
    """Evaluate a whitelisted refinement-AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in bindings:
            return bindings[node.id]
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        if node.id in _ALLOWED_FUNCTIONS:
            return _ALLOWED_FUNCTIONS[node.id]
        raise RefinementSyntaxError(f"unbound name in refinement: {node.id!r}")
    if isinstance(node, ast.UnaryOp):
        op = type(node.op).__name__
        v = _eval_node(node.operand, bindings)
        if op == "Not":
            return not v
        if op == "USub":
            return -v
        if op == "UAdd":
            return +v
        raise RefinementSyntaxError(f"unsupported unary op: {op}")
    if isinstance(node, ast.BinOp):
        fn = _BINOP_FN.get(type(node.op))
        if fn is None:
            raise RefinementSyntaxError(f"unsupported binop: {type(node.op).__name__}")
        return fn(_eval_node(node.left, bindings), _eval_node(node.right, bindings))
    if isinstance(node, ast.BoolOp):
        op = type(node.op).__name__
        vals = [_eval_node(v, bindings) for v in node.values]
        if op == "And":
            result = True
            for v in vals:
                if not v:
                    return False
                result = v
            return bool(result)
        if op == "Or":
            for v in vals:
                if v:
                    return v
            return False
        raise RefinementSyntaxError(f"unsupported bool op: {op}")
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, bindings)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, bindings)
            fn = _CMP_FN.get(type(op_node))
            if fn is None:
                raise RefinementSyntaxError(f"unsupported compare: {type(op_node).__name__}")
            if not fn(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e, bindings) for e in node.elts)
    if isinstance(node, ast.List):
        return [_eval_node(e, bindings) for e in node.elts]
    if isinstance(node, ast.Call):
        func = _eval_node(node.func, bindings)
        args = [_eval_node(a, bindings) for a in node.args]
        if not callable(func):
            raise RefinementSyntaxError("refinement called non-callable")
        return func(*args)
    raise RefinementSyntaxError(f"refinement uses unsupported node type: {type(node).__name__}")


# --- direct fast paths for common shapes ---------------------------------
# v2.7 fix (per swarm code-critic, finding #15): dropped the unused `name`
# parameter from each fast-path function. The name was a leftover from a
# planned binding-lookup design that was never implemented.


def eval_eq_zero(value: int) -> bool:
    """Inline-fast: ``<expr>≠0`` evaluation. Unboxed integer compare."""
    return value != 0


def eval_lt_const(value: int, k: int) -> bool:
    """Inline-fast: ``<expr> < k`` evaluation."""
    return value < k


def eval_len_gt_zero(seq: Any) -> bool:
    """Inline-fast: ``|<expr>|>0`` evaluation."""
    return len(seq) > 0


def eval_in_set(value: Any, options: tuple[Any, ...]) -> bool:
    """Inline-fast: ``<expr> ∈ {...}`` evaluation."""
    return value in options
