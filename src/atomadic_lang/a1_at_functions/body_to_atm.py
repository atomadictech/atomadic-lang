"""Tier a1 — pure conversion of a Python function body AST to an .atm expression.

Handles the v0 / v0.6 / v0.8 subset:
  - single-return bodies → inline form
  - if-raise-then-return bodies → refinement form
  - multi-statement bodies → sequence form ``(s1 ; s2 ; ... ; ret)`` (v0.6)
  - assign / aug-assign / ann-assign in body (v0.6)
  - if/else with both branches return → ternary expr (v0.6)
  - ternary expressions (``x if cond else y``) → ``cond?x:y`` (v0.6)
  - bare-call statements (e.g. ``print(x)``) inside sequence (v0.6)
  - **f-strings** (``f"hi {x}"``) → ``s"hi ⟦x⟧"`` (v0.8)
  - **list comprehensions** (``[e for x in xs]``) → ``[e | x ∈ xs]`` (v0.8)
  - **dict / set / generator comprehensions** → analogous (v0.8)
  - **lambdas** (``lambda x: x*2``) → ``x↦x*2`` (v0.8)
  - simple BinOp / Compare / Call / Name / Constant expressions

Unsupported constructs lower to a structural placeholder rather than failing.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from ..a0_qk_constants.atm_grammar import PY_BINOP_TO_ATM, PY_CMPOP_TO_ATM


@dataclass(frozen=True)
class BodyLowering:
    """Result of lowering a function body."""

    pre: str        # "" if absent
    post: str       # "" if absent
    body: str       # the body expression (inline) or the literal source (placeholder)
    form: str       # "inline" | "refinement" | "structural"


def lower_function_body(body: list[ast.stmt]) -> BodyLowering:
    """Lower a list of Python statements (a function body) to an .atm body.

    Three forms recognised, in priority order:

    1. **Refinement**: leading ``if cond: raise ValueError(...)`` followed by a
       single ``return expr``. Lowered as ``pre ¬cond ; body expr``.
    2. **Inline**: a single ``return expr``. Lowered as ``= expr``.
    3. **Structural**: anything else. The body is rendered as the original
       Python source (best-effort) wrapped in a structural marker. This keeps
       the lowerer total — no input is rejected — at the cost of density.
    """
    if not body:
        return BodyLowering(pre="", post="", body="∅", form="inline")

    # Strip a leading docstring if present.
    work = list(body)
    if isinstance(work[0], ast.Expr) and isinstance(work[0].value, ast.Constant) and isinstance(work[0].value.value, str):
        work = work[1:]

    if not work:
        return BodyLowering(pre="", post="", body="∅", form="inline")

    # Pattern 1: if-raise + return
    if (
        len(work) == 2
        and isinstance(work[0], ast.If)
        and _is_guard_raise(work[0])
        and isinstance(work[1], ast.Return)
        and work[1].value is not None
    ):
        guard = work[0]
        # The negation of the guard becomes the precondition.
        pre_expr = _negate_expr(guard.test)
        body_expr = lower_expr(work[1].value)
        return BodyLowering(pre=pre_expr, post="", body=body_expr, form="refinement")

    # Pattern 2: single return
    if len(work) == 1 and isinstance(work[0], ast.Return) and work[0].value is not None:
        body_expr = lower_expr(work[0].value)
        return BodyLowering(pre="", post="", body=body_expr, form="inline")

    # Pattern 2b: single if/else with both branches return → ternary.
    if len(work) == 1 and _is_if_then_else_return(work[0]):
        body_expr = _ifreturn_to_ternary(work[0])  # type: ignore[arg-type]
        if body_expr is not None:
            return BodyLowering(pre="", post="", body=body_expr, form="inline")

    # Pattern 3 (v0.6): multi-statement body of recognised stmts ending in return.
    # Lowers to a sequence form ``(s1 ; s2 ; ... ; ret_expr)``.
    seq = _try_lower_sequence(work)
    if seq is not None:
        return BodyLowering(pre="", post="", body=seq, form="inline")

    # Pattern 4: structural fallback — preserve the source via ast.unparse.
    # Newlines inside structural bodies are escaped to keep each decl on
    # one line (line-based parser depends on this).
    try:
        src = "; ".join(ast.unparse(s).replace("\n", "\\n") for s in work)
    except Exception:
        src = "<unsupported body>"
    return BodyLowering(pre="", post="", body=f"⟪{src}⟫", form="structural")


def _try_lower_sequence(stmts: list[ast.stmt]) -> str | None:
    """Lower a sequence of body statements to ``(s1 ; s2 ; ... ; ret_expr)``.

    Returns None if any statement is not in the recognised set. Recognised:

    - ``Assign`` (single-target name) → ``name=expr``
    - ``AnnAssign`` (single-target name with value) → ``name=expr`` (type-sigil dropped in body for v0.6)
    - ``AugAssign`` → ``name=name op expr``
    - ``Expr`` of ``Call`` → bare call (e.g. ``print(x)``)
    - ``If`` with both branches single-return → ternary, but only as the *final* statement
    - ``Return`` (must be final and non-None)
    - ``Raise`` of a ``Call`` → ``!"msg"`` (terminates the sequence)
    """
    if not stmts:
        return None

    parts: list[str] = []
    final = stmts[-1]

    # Walk middle statements (everything except the final one).
    for stmt in stmts[:-1]:
        rendered = _lower_middle_stmt(stmt)
        if rendered is None:
            return None
        parts.append(rendered)

    # Final statement must be a Return, a tail-If(both-return), or a Raise.
    if isinstance(final, ast.Return):
        if final.value is None:
            parts.append("∅")
        else:
            parts.append(lower_expr(final.value))
    elif _is_if_then_else_return(final):
        ternary = _ifreturn_to_ternary(final)  # type: ignore[arg-type]
        if ternary is None:
            return None
        parts.append(ternary)
    elif isinstance(final, ast.Raise):
        rendered = _lower_raise(final)
        if rendered is None:
            return None
        parts.append(rendered)
    else:
        # No final return — could be an implicit-None procedure. v0.6 treats this
        # as still-recognised iff every statement was a recognised middle-stmt.
        rendered = _lower_middle_stmt(final)
        if rendered is None:
            return None
        parts.append(rendered)
        parts.append("∅")  # implicit None tail

    return "(" + " ; ".join(parts) + ")"


def _lower_middle_stmt(stmt: ast.stmt) -> str | None:
    """Lower one body statement (not the final return). Returns None if unrecognised."""
    # Plain assign: x = expr OR self.x = expr (single target, name or attribute)
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target = stmt.targets[0]
        if isinstance(target, ast.Name):
            return f"{target.id}={lower_expr(stmt.value)}"
        if isinstance(target, ast.Attribute):
            return f"{lower_expr(target)}={lower_expr(stmt.value)}"
        if isinstance(target, ast.Subscript):
            return f"{lower_expr(target)}={lower_expr(stmt.value)}"

    # Annotated assign: x: T = expr OR self.x: T = expr
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        if isinstance(stmt.target, ast.Name):
            return f"{stmt.target.id}={lower_expr(stmt.value)}"
        if isinstance(stmt.target, ast.Attribute):
            return f"{lower_expr(stmt.target)}={lower_expr(stmt.value)}"

    # Augmented: x += expr OR self.x += expr → expr=expr op rhs
    if isinstance(stmt, ast.AugAssign):
        op = PY_BINOP_TO_ATM.get(type(stmt.op).__name__, "?")
        if isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            return f"{name}={name}{op}{lower_expr(stmt.value)}"
        if isinstance(stmt.target, ast.Attribute):
            tgt = lower_expr(stmt.target)
            return f"{tgt}={tgt}{op}{lower_expr(stmt.value)}"

    # Bare expression (e.g., function call as a statement).
    if isinstance(stmt, ast.Expr):
        return lower_expr(stmt.value)

    # Raise as a non-final statement (rare but valid — sequence after raise is dead).
    if isinstance(stmt, ast.Raise):
        return _lower_raise(stmt)

    # Pass — emit nothing.
    if isinstance(stmt, ast.Pass):
        return "∅"

    # try/except — v0.9 lowering as `expr catch ExcName(var) ⇒ handler` form.
    if isinstance(stmt, ast.Try):
        return _lower_try_stmt(stmt)

    # with-statement — v0.9 lowering as `with binding body` form.
    if isinstance(stmt, ast.With) or isinstance(stmt, ast.AsyncWith):
        return _lower_with_stmt(stmt)

    return None


def _lower_raise(node: ast.Raise) -> str | None:
    """Lower a Raise statement to ``!"msg"`` form."""
    if node.exc is None:
        return "!"
    # raise SomeExc("msg") → !"msg"
    if isinstance(node.exc, ast.Call) and node.exc.args:
        first = node.exc.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return f'!"{first.value}"'
        return f"!{lower_expr(first)}"
    # raise ExcName → !"ExcName"
    if isinstance(node.exc, ast.Name):
        return f'!"{node.exc.id}"'
    return f"!{lower_expr(node.exc)}"


def _is_if_then_else_return(node: ast.stmt) -> bool:
    """True if ``node`` is ``if cond: return X else: return Y`` (both branches single-return)."""
    if not isinstance(node, ast.If):
        return False
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
        return False
    if not node.orelse or len(node.orelse) != 1:
        return False
    return isinstance(node.orelse[0], ast.Return)


def _ifreturn_to_ternary(node: ast.If) -> str | None:
    """Convert ``if cond: return X else: return Y`` to ``cond?X:Y``."""
    then_ret = node.body[0]
    else_ret = node.orelse[0]
    if not isinstance(then_ret, ast.Return) or then_ret.value is None:
        return None
    if not isinstance(else_ret, ast.Return) or else_ret.value is None:
        return None
    cond = lower_expr(node.test)
    then_ = lower_expr(then_ret.value)
    else_ = lower_expr(else_ret.value)
    return f"{cond}?{then_}:{else_}"


def _is_guard_raise(node: ast.If) -> bool:
    """Return True if `node` is ``if <cond>: raise <something>`` with no else."""
    if node.orelse:
        return False
    if len(node.body) != 1:
        return False
    inner = node.body[0]
    return isinstance(inner, ast.Raise)


def _negate_expr(node: ast.expr) -> str:
    """Render the *negation* of a Python expression as an .atm expression.

    v2.6 fix (per swarm code-critic): BoolOp guards (`a==0 or b==0`) were
    previously falling through to `¬<expr>` without parens, producing
    `¬a≟0∨b≟0` (wrong precedence — silent corruption). Now applies De Morgan
    to BoolOp and parenthesises any ambiguous fallthrough.
    """
    # Single comparator flip (common case): a==0 → a≠0
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        op = type(node.ops[0]).__name__
        flipped = {
            "Eq": "≠",
            "NotEq": "≟",
            "Lt": "≥",
            "LtE": ">",
            "Gt": "≤",
            "GtE": "<",
            "In": "∉",
            "NotIn": "∈",
        }.get(op)
        if flipped is not None:
            left = lower_expr(node.left)
            right = lower_expr(node.comparators[0])
            return f"{left}{flipped}{right}"

    # De Morgan on BoolOp: ¬(a∧b) → ¬a ∨ ¬b ; ¬(a∨b) → ¬a ∧ ¬b
    if isinstance(node, ast.BoolOp):
        op_name = type(node.op).__name__
        new_op = "∨" if op_name == "And" else "∧"
        return new_op.join(_negate_expr(v) for v in node.values)

    # Double-negation: ¬¬x → x
    if isinstance(node, ast.UnaryOp) and type(node.op).__name__ == "Not":
        return lower_expr(node.operand)

    # Fallback: ¬(<expr>) — explicit parens to avoid precedence drift.
    return f"¬({lower_expr(node)})"


def lower_expr(node: ast.expr) -> str:
    """Render a Python expression AST as an .atm expression string."""
    # Constants
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "∅"
        if isinstance(v, str):
            # Escape control chars + the double-quote so the string survives
            # round-trip through a line-based parser.
            esc = (
                v.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\n", "\\n")
                 .replace("\r", "\\r")
                 .replace("\t", "\\t")
            )
            return f'"{esc}"'
        return str(v)

    # Names
    if isinstance(node, ast.Name):
        return node.id

    # BinOp: a + b
    if isinstance(node, ast.BinOp):
        op = PY_BINOP_TO_ATM.get(type(node.op).__name__, "?")
        left = lower_expr(node.left)
        right = lower_expr(node.right)
        return f"{left}{op}{right}"

    # UnaryOp: -x, not x
    if isinstance(node, ast.UnaryOp):
        op_name = type(node.op).__name__
        operand = lower_expr(node.operand)
        if op_name == "USub":
            return f"-{operand}"
        if op_name == "Not":
            return f"¬{operand}"
        if op_name == "UAdd":
            return operand
        return f"{op_name}({operand})"

    # Compare: a < b, a == b
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        op = PY_CMPOP_TO_ATM.get(type(node.ops[0]).__name__, "?")
        left = lower_expr(node.left)
        right = lower_expr(node.comparators[0])
        return f"{left}{op}{right}"

    # BoolOp: a and b, a or b
    if isinstance(node, ast.BoolOp):
        op = "∧" if type(node.op).__name__ == "And" else "∨"
        return op.join(lower_expr(v) for v in node.values)

    # IfExp (ternary): x if cond else y → cond?x:y (v0.6)
    if isinstance(node, ast.IfExp):
        cond = lower_expr(node.test)
        then_ = lower_expr(node.body)
        else_ = lower_expr(node.orelse)
        return f"{cond}?{then_}:{else_}"

    # JoinedStr (f-string): f"hi {x}!" → s"hi ⟦x⟧!" (v0.8)
    if isinstance(node, ast.JoinedStr):
        return _lower_fstring(node)

    # ListComp: [e for x in xs if cond] → [e | x ∈ xs ? cond] (v0.8)
    if isinstance(node, ast.ListComp):
        return f"[{_lower_comp_body(node.elt, node.generators)}]"

    # SetComp: {e for x in xs} → {e | x ∈ xs} (v0.8)
    if isinstance(node, ast.SetComp):
        return f"{{{_lower_comp_body(node.elt, node.generators)}}}"

    # GeneratorExp: (e for x in xs) → (e | x ∈ xs) (v0.8)
    if isinstance(node, ast.GeneratorExp):
        return f"({_lower_comp_body(node.elt, node.generators)})"

    # DictComp: {k: v for x in xs} → {k:v | x ∈ xs} (v0.8)
    if isinstance(node, ast.DictComp):
        kv = f"{lower_expr(node.key)}:{lower_expr(node.value)}"
        gens = _lower_comp_generators(node.generators)
        return f"{{{kv} | {gens}}}"

    # Lambda: lambda x: expr → x↦expr; lambda a,b: expr → (a,b)↦expr (v0.8)
    if isinstance(node, ast.Lambda):
        return _lower_lambda(node)

    # Compare with chained comparators: a < b < c → a<b ∧ b<c (v0.6)
    if isinstance(node, ast.Compare) and len(node.ops) >= 2:
        parts: list[str] = []
        prev = node.left
        for op_node, comp in zip(node.ops, node.comparators):
            sym = PY_CMPOP_TO_ATM.get(type(op_node).__name__, "?")
            parts.append(f"{lower_expr(prev)}{sym}{lower_expr(comp)}")
            prev = comp
        return "∧".join(parts)

    # Call: f(a, b, kw=v) — v0.9 added keyword-argument support
    if isinstance(node, ast.Call):
        func = lower_expr(node.func)
        parts: list[str] = [lower_expr(a) for a in node.args]
        # Splatted: f(*xs) → "*xs", f(**kw) → "**kw" (best-effort surface)
        for kw in node.keywords:
            if kw.arg is None:
                # **kwargs splat
                parts.append(f"**{lower_expr(kw.value)}")
            else:
                parts.append(f"{kw.arg}={lower_expr(kw.value)}")
        return f"{func}({','.join(parts)})"

    # Attribute access: a.b
    if isinstance(node, ast.Attribute):
        return f"{lower_expr(node.value)}.{node.attr}"

    # Subscript: a[b]
    if isinstance(node, ast.Subscript):
        return f"{lower_expr(node.value)}[{lower_expr(node.slice)}]"

    # List literal: [1, 2, 3]
    if isinstance(node, ast.List):
        inner = ",".join(lower_expr(e) for e in node.elts)
        return f"[{inner}]"

    # Tuple literal: (a, b)
    if isinstance(node, ast.Tuple):
        inner = ",".join(lower_expr(e) for e in node.elts)
        return f"({inner})"

    # Fallback: render via unparse, wrapped to mark non-standard.
    # Escape newlines so structural fragments don't break line-based parsing.
    try:
        return f"⟪{ast.unparse(node).replace(chr(10), chr(92) + 'n')}⟫"
    except Exception:
        return "⟪?⟫"


# --- v0.8 helpers --------------------------------------------------------


def _lower_fstring(node: ast.JoinedStr) -> str:
    """Lower an f-string to ``s"...⟦expr⟧..."`` form.

    JoinedStr.values is a list of Constant (literal text) and FormattedValue
    (substitution). For v0.8 we drop ``!r``/``!s``/``!a`` conversions and
    keep the format spec inside the brackets when present.
    """
    parts: list[str] = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            # Escape control chars + double-quote so the f-string survives
            # round-trip through the line-based parser.
            esc = (
                v.value.replace("\\", "\\\\")
                       .replace('"', '\\"')
                       .replace("\n", "\\n")
                       .replace("\r", "\\r")
                       .replace("\t", "\\t")
            )
            parts.append(esc)
        elif isinstance(v, ast.FormattedValue):
            inner = lower_expr(v.value)
            if v.format_spec is not None and isinstance(v.format_spec, ast.JoinedStr):
                fmt = "".join(
                    c.value for c in v.format_spec.values
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)
                )
                parts.append(f"⟦{inner}:{fmt}⟧")
            else:
                parts.append(f"⟦{inner}⟧")
        else:
            try:
                parts.append(ast.unparse(v).replace("\n", "\\n"))
            except Exception:
                parts.append("⟦?⟧")
    body = "".join(parts)
    return f's"{body}"'


def _lower_comp_body(elt: ast.expr, generators: list[ast.comprehension]) -> str:
    """Lower the body of a list/set/gen comprehension: ``elt | gens``."""
    return f"{lower_expr(elt)} | {_lower_comp_generators(generators)}"


def _lower_comp_generators(gens: list[ast.comprehension]) -> str:
    """Lower the comprehension's generator clauses to ``x ∈ xs ? cond, y ∈ ys``."""
    parts: list[str] = []
    for g in gens:
        target = _lower_comp_target(g.target)
        iter_ = lower_expr(g.iter)
        clause = f"{target}∈{iter_}"
        for cond in g.ifs:
            clause += f" ? {lower_expr(cond)}"
        parts.append(clause)
    return ", ".join(parts)


def _lower_comp_target(node: ast.expr) -> str:
    """Lower the target side of a `for` clause (Name or Tuple-of-Names)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Tuple):
        return "(" + ",".join(
            (n.id if isinstance(n, ast.Name) else lower_expr(n))
            for n in node.elts
        ) + ")"
    return lower_expr(node)


def _lower_lambda(node: ast.Lambda) -> str:
    """Lower ``lambda x: body`` to ``x↦body``; ``lambda a,b: body`` to ``(a,b)↦body``."""
    args = node.args.args
    body = lower_expr(node.body)
    if len(args) == 1:
        return f"{args[0].arg}↦{body}"
    if not args:
        return f"()↦{body}"
    return "(" + ",".join(a.arg for a in args) + f")↦{body}"


def _lower_try_stmt(node: ast.Try) -> str | None:
    """Lower ``try: body except E as v: handler`` (v0.9).

    Produces ``(body) catch ExcName(var) ⇒ (handler)``; supports a single
    handler clause for v0.9. Multiple handlers / `else`/`finally` fall back
    to structural by returning None.
    """
    if not node.handlers or len(node.handlers) > 1:
        return None
    if node.orelse or node.finalbody:
        return None

    handler = node.handlers[0]

    # Lower the body (may itself be a sequence)
    body_str = _lower_block_as_expr(node.body)
    if body_str is None:
        return None

    # Lower the handler block
    handler_str = _lower_block_as_expr(handler.body)
    if handler_str is None:
        return None

    # Exception clause: `ExcName(var)` if `except E as v` else `ExcName`.
    if handler.type is None:
        exc = "_"  # bare except
    elif isinstance(handler.type, ast.Name):
        exc = handler.type.id
    else:
        exc = lower_expr(handler.type)
    if handler.name:
        exc = f"{exc}({handler.name})"

    return f"({body_str}) catch {exc} ⇒ ({handler_str})"


def _lower_with_stmt(node: ast.With | ast.AsyncWith) -> str | None:
    """Lower ``with ctx as name: body`` (v0.9).

    Produces ``with binding body``. Supports single-context and tuple-of-contexts.
    Multi-statement body lowers via the recognised-sequence path; if any
    statement is unlowerable, returns None and falls to structural.
    """
    body_str = _lower_block_as_expr(node.body)
    if body_str is None:
        return None

    bindings: list[str] = []
    for item in node.items:
        ctx = lower_expr(item.context_expr)
        if item.optional_vars is None:
            bindings.append(ctx)
        elif isinstance(item.optional_vars, ast.Name):
            bindings.append(f"{item.optional_vars.id}={ctx}")
        else:
            # Tuple etc. — render via lower_expr fallback
            bindings.append(f"{lower_expr(item.optional_vars)}={ctx}")

    if len(bindings) == 1:
        return f"with {bindings[0]} ({body_str})"
    return f"with ({','.join(bindings)}) ({body_str})"


def _lower_block_as_expr(stmts: list[ast.stmt]) -> str | None:
    """Lower a list of statements as an expression (sequence form for multi-stmt).

    Returns None if any statement is unrecognised — callers fall back to structural.
    """
    if not stmts:
        return "∅"
    # Single Return / single Raise / single Expression: render directly.
    if len(stmts) == 1:
        first = stmts[0]
        if isinstance(first, ast.Return) and first.value is not None:
            return lower_expr(first.value)
        if isinstance(first, ast.Return) and first.value is None:
            return "∅"
        if isinstance(first, ast.Raise):
            return _lower_raise(first)
        rendered = _lower_middle_stmt(first)
        if rendered is None:
            return None
        return rendered
    # Multi-statement block: reuse the sequence lowerer.
    seq = _try_lower_sequence(stmts)
    if seq is None:
        return None
    # Strip outer parens — caller will add its own structure.
    return seq[1:-1] if seq.startswith("(") and seq.endswith(")") else seq
