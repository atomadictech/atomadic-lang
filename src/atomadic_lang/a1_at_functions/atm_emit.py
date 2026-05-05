"""Tier a1 — pure assembly of lowered declarations into .atm source text.

Takes ``LoweredDecl`` records and emits the surface form per SPEC_v0.md.
"""

from __future__ import annotations

from ..a0_qk_constants.atm_grammar import (
    ARROW,
    PACKAGE_MARKER,
    PARAM_CLOSE,
    PARAM_OPEN,
)
from ..a0_qk_constants.atm_types import LoweredDecl


def emit_param(name: str, type_sigil: str) -> str:
    """Emit a single ``name:type`` parameter token."""
    return f"{name}:{type_sigil}"


def emit_params(params: list[dict]) -> str:
    """Emit the ``⟨a:i b:i⟩`` parameter block."""
    if not params:
        return f"{PARAM_OPEN}{PARAM_CLOSE}"
    body = " ".join(emit_param(p["name"], p["type_sigil"]) for p in params)
    return f"{PARAM_OPEN}{body}{PARAM_CLOSE}"


def emit_decl(decl: LoweredDecl) -> str:
    """Emit a single declaration as one or more lines of .atm source."""
    head = f"{decl['tier']}{decl['effect']} {decl['name']}"

    # Class field declaration: `2σ ClassName ⟨field:i field:s⟩` — no arrow, no body.
    if decl["body_form"] == "class":
        sig = emit_params(decl["params"])
        return f"{head} {sig}"

    if decl["tier"] == 0:
        # Constant or enum form. v2.7 fix (caught by hand-written round-trip
        # test): only emit ``: <sigil>`` when a return sigil exists. Enum form
        # has no sigil — was previously emitting ``0 OP :  = enum{...}`` with
        # an empty colon-type.
        if decl["params"]:
            sig = emit_params(decl["params"])
            head += f" {sig}{ARROW}{decl['return_sigil']}"
        elif decl["return_sigil"]:
            head += f" : {decl['return_sigil']}"
        return f"{head} = {decl['body']}"

    # Tier 1+: function-shaped.
    sig = emit_params(decl["params"])
    head += f" {sig}{ARROW}{decl['return_sigil']}"

    if decl["body_form"] == "inline":
        return f"{head} = {decl['body']}"

    if decl["body_form"] == "refinement":
        lines = [head]
        if decl["pre"]:
            lines.append(f"  pre {decl['pre']}")
        if decl["post"]:
            lines.append(f"  post {decl['post']}")
        if decl["body"]:
            lines.append(f"  body {decl['body']}")
        return "\n".join(lines)

    # Structural fallback.
    return f"{head} = {decl['body']}"


def emit_module(package: str, decls: list[LoweredDecl]) -> str:
    """Emit the full .atm module text."""
    lines: list[str] = [f"{PACKAGE_MARKER}{package}", ""]
    # Group by tier for readability (constants first, then a1, …).
    by_tier: dict[int, list[LoweredDecl]] = {}
    for d in decls:
        by_tier.setdefault(d["tier"], []).append(d)
    first_group = True
    for tier in sorted(by_tier):
        if not first_group:
            lines.append("")
        first_group = False
        for d in by_tier[tier]:
            lines.append(emit_decl(d))
    return "\n".join(lines) + "\n"


def count_atm_tokens(source: str) -> int:
    """Cheap token count for .atm source.

    Splits on whitespace; treats sigil characters (``→``, ``▷``, ``⟨``,
    ``⟩``, ``=``, etc.) as separate tokens; collapses runs of operator
    characters into one token. Used for v0 density measurement only —
    NOT the production tokenizer (that's a v0.5 deliverable).
    """
    # Replace structural sigils with surrounding spaces so they tokenize separately.
    sigils = ["→", "▷", "⟨", "⟩", "=", ":", ",", "@", "(", ")", "[", "]", "{", "}"]
    s = source
    for sig in sigils:
        s = s.replace(sig, f" {sig} ")
    return len([t for t in s.split() if t])


def count_py_tokens(source: str) -> int:
    """Cheap token count for Python source.

    Uses ``tokenize`` module if available; falls back to whitespace+punct
    splitting. NOT the production tokenizer; v0 density-measurement only.
    """
    try:
        import io
        import tokenize

        count = 0
        for tok in tokenize.tokenize(io.BytesIO(source.encode("utf-8")).readline):
            if tok.type in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
                            tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER,
                            tokenize.COMMENT):
                continue
            if not tok.string.strip():
                continue
            count += 1
        return count
    except Exception:
        # Fallback: whitespace+punct split.
        sigils = [":", "(", ")", ",", "=", "->", "+", "-", "*", "/", "[", "]"]
        s = source
        for sig in sigils:
            s = s.replace(sig, f" {sig} ")
        return len([t for t in s.split() if t])
