"""Tier a1 — pure parser for the v0..v0.9 `.atm` surface.

Parses `.atm` source text back to ``LoweredDecl`` records — the same shape
``lower_feature`` produces. This is the inverse of ``atm_emit.emit_module``.
Closes the round-trip ``lower(py) → emit → raise → emit == original_emit``.

For v1.0 the parser captures structural fields (tier, effect, name, params,
return_sigil, body_form, body, pre, post). Bodies remain raw strings —
sufficient for round-trip and for downstream tools that need the AST shape
without semantic validation.

Imports a0 only.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..a0_qk_constants.atm_grammar import (
    EFFECT_SIGIL_TO_ASCII,
    TIER_DEFAULT_EFFECT_SIGIL,
)
from ..a0_qk_constants.atm_types import LoweredDecl, LoweredModule, LoweredParam


# All recognised effect sigils, in a single character class for the head regex.
_EFFECT_CHARS = "πσωιλ"

# Head-line regex. Captures: tier-digit, optional effect sigil, name, then
# the rest (params / return / body). The rest is parsed by a small state
# machine because it has multiple optional / interleaved pieces.
_HEAD_RE = re.compile(
    rf"^\s*(?P<tier>[0-4])(?P<effect>[{_EFFECT_CHARS}])?\s+(?P<name>[A-Za-z_][\w.]*)(?P<rest>.*)$"
)

# Param entry: ``name:typesigil``. The type sigil may be a complex expression
# (e.g. ``[s]``, ``{i:s}``, ``Counter``). Anything that is not whitespace.
_PARAM_RE = re.compile(r"([A-Za-z_]\w*)\s*:\s*(\S+)")


def parse_module(atm_text: str) -> LoweredModule:
    """Parse a full `.atm` module text into a LoweredModule.

    The first non-empty, non-blank line should be ``@<package>``. Subsequent
    declarations follow until end-of-text. Indented lines following a head
    line are treated as continuation (refinement clauses).
    """
    package = "_unknown"
    decls: list[LoweredDecl] = []
    chars = len(atm_text)

    for head_line, cont_lines in _iter_decl_blocks(atm_text):
        if head_line.startswith("@"):
            package = head_line[1:].strip() or package
            continue
        decl = parse_decl(head_line, cont_lines)
        if decl is not None:
            decls.append(decl)

    return LoweredModule(
        schema_version="atomadic-lang.lower/v0",
        package=package,
        decls=decls,
        py_token_count=0,
        atm_token_count=chars,  # cheap proxy — caller may recompute
        density_ratio=0.0,
    )


def parse_decl(head_line: str, cont_lines: list[str] | None = None) -> LoweredDecl | None:
    """Parse one declaration's head + optional continuation lines.

    Returns None if the head doesn't match a declaration shape (e.g. it's
    a stray comment or whitespace).
    """
    cont_lines = cont_lines or []
    m = _HEAD_RE.match(head_line)
    if m is None:
        return None

    tier = int(m.group("tier"))
    effect = m.group("effect") or ""
    name = m.group("name")
    rest = m.group("rest").strip()

    # Decide effect for tier-0 (no sigil emitted).
    if tier == 0 and effect == "":
        effect_out = ""
    else:
        # If no explicit effect, use the tier's default.
        effect_out = effect or TIER_DEFAULT_EFFECT_SIGIL.get(tier, "")

    params, rest = _parse_params_block(rest)
    return_sigil, rest = _parse_return_section(rest, tier=tier)
    body, body_form, pre, post = _parse_body(rest, cont_lines, tier=tier, has_params=bool(params))

    return LoweredDecl(
        tier=tier,                          # type: ignore[typeddict-item]
        effect=effect_out,                   # type: ignore[typeddict-item]
        name=name,
        params=params,
        return_sigil=return_sigil,
        body_form=body_form,                 # type: ignore[typeddict-item]
        body=body,
        pre=pre,
        post=post,
        source_path="<parsed>",
        source_lineno=0,
    )


def _parse_params_block(rest: str) -> tuple[list[LoweredParam], str]:
    """If `rest` starts with ⟨…⟩, consume the params block and return (params, remainder)."""
    if not rest.startswith("⟨"):
        return [], rest
    end = rest.find("⟩")
    if end < 0:
        return [], rest  # malformed — treat as no params
    inside = rest[1:end]
    after = rest[end + 1 :].strip()
    params: list[LoweredParam] = []
    for pm in _PARAM_RE.finditer(inside):
        params.append(LoweredParam(name=pm.group(1), type_sigil=pm.group(2)))
    return params, after


def _parse_return_section(rest: str, *, tier: int) -> tuple[str, str]:
    """Consume ``→<sigil>`` or (tier-0 only) ``: <sigil>`` and return (sigil, remainder)."""
    if rest.startswith("→"):
        rest_after = rest[1:].lstrip()
        m = re.match(r"\S+", rest_after)
        if m is None:
            return "_", rest_after
        sig = m.group(0)
        # Trim trailing `=` if it was glued (e.g. `→i=a+b`)
        if sig.endswith("="):
            sig = sig[:-1]
            return sig, "=" + rest_after[len(sig) + 1 :]
        return sig, rest_after[len(sig) :].lstrip()

    if tier == 0 and rest.startswith(":"):
        rest_after = rest[1:].lstrip()
        m = re.match(r"\S+", rest_after)
        if m is None:
            return "_", rest_after
        sig = m.group(0)
        return sig, rest_after[len(sig) :].lstrip()

    return "", rest


def _parse_body(
    rest: str,
    cont_lines: list[str],
    *,
    tier: int,
    has_params: bool,
) -> tuple[str, str, str, str]:
    """Decide body_form and parse body / pre / post fields.

    Returns ``(body, body_form, pre, post)``.
    """
    # Continuation lines mean refinement form.
    if cont_lines:
        pre = ""
        post = ""
        body = ""
        for line in cont_lines:
            stripped = line.strip()
            if stripped.startswith("pre "):
                pre = stripped[4:].strip()
            elif stripped.startswith("post "):
                post = stripped[5:].strip()
            elif stripped.startswith("body "):
                body = stripped[5:].strip()
        return body, "refinement", pre, post

    # Inline body: starts with `=`
    if rest.startswith("="):
        body = rest[1:].lstrip()
        return body, "inline", "", ""

    # No `=` and we DO have params → class form (no return type, no body).
    if has_params and not rest:
        return "", "class", "", ""

    # Tier-0 const form already had `:` consumed; the body comes after `=`.
    # If we got here with non-empty `rest` that doesn't start with `=`,
    # treat it as a structural fallback.
    if rest:
        return rest, "structural", "", ""

    # Empty rest: tier-0 with no body, or class with no params — both default.
    return "", "class", "", ""


def _iter_decl_blocks(atm_text: str) -> Iterator[tuple[str, list[str]]]:
    """Iterate (head_line, continuation_lines) tuples for each decl block.

    A continuation line is any indented line immediately following a head
    line. Empty lines and the package marker (``@<name>``) are also yielded
    as head lines (with empty continuations) — the caller dispatches.
    """
    lines = atm_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line[0].isspace():
            # Stray indented line with no head — skip.
            i += 1
            continue
        head = line.rstrip()
        cont: list[str] = []
        j = i + 1
        while j < len(lines) and lines[j].startswith(" ") and lines[j].strip():
            cont.append(lines[j].rstrip())
            j += 1
        yield head, cont
        i = j


def normalize_effect_sigil(sigil: str) -> str:
    """Return the canonical Unicode effect sigil for a one-char input.

    Accepts both Unicode (``π``) and ASCII fallback (``p``); returns Unicode.
    """
    if sigil in EFFECT_SIGIL_TO_ASCII:
        return sigil  # already canonical
    inverse = {v: k for k, v in EFFECT_SIGIL_TO_ASCII.items()}
    return inverse.get(sigil, sigil)
