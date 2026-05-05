"""Tier a0 — state-machine states for the .atm grammar mask evaluator.

Used by the v2.0 §1 latency benchmark. Each state corresponds to a
position in the .atm declaration grammar where the legal-next-token set
is bounded and quickly computable.
"""

from __future__ import annotations

from typing import Final


# Grammar phases — each is a coarse "where am I in a declaration" state.
# The mask evaluator transitions between these as tokens are emitted.

MODULE_START: Final[str] = "MODULE_START"
"""Awaiting `@<package>` or end of file."""

DECL_START: Final[str] = "DECL_START"
"""Awaiting tier digit + (optional) effect sigil."""

DECL_NAME: Final[str] = "DECL_NAME"
"""Tier+effect emitted, awaiting declaration name (identifier)."""

PARAMS_OPEN: Final[str] = "PARAMS_OPEN"
"""After name, awaiting `⟨` to open params (or `:` for tier-0 const, or `=` for inline body)."""

PARAM_NAME: Final[str] = "PARAM_NAME"
"""Inside params, awaiting parameter name."""

PARAM_COLON: Final[str] = "PARAM_COLON"
"""After param name, awaiting `:`."""

PARAM_TYPE: Final[str] = "PARAM_TYPE"
"""After `:`, awaiting type sigil."""

PARAM_SEP_OR_CLOSE: Final[str] = "PARAM_SEP_OR_CLOSE"
"""After param type, awaiting space (next param) or `⟩`."""

ARROW_OR_BODY: Final[str] = "ARROW_OR_BODY"
"""After `⟩`, awaiting `→` (return type) or end-of-decl (class form)."""

RETURN_TYPE: Final[str] = "RETURN_TYPE"
"""After `→`, awaiting return type sigil."""

EQUALS_OR_REFINEMENT: Final[str] = "EQUALS_OR_REFINEMENT"
"""After return type, awaiting `=` (inline) or newline+indent (refinement clauses)."""

INLINE_BODY: Final[str] = "INLINE_BODY"
"""After `=`, body is a free expression — the mask is unrestricted on grammar."""

REFINEMENT_CLAUSE: Final[str] = "REFINEMENT_CLAUSE"
"""On indented continuation: awaiting `pre`/`post`/`body`."""


# Ordered tuple for indexing.
ALL_STATES: Final[tuple[str, ...]] = (
    MODULE_START,
    DECL_START,
    DECL_NAME,
    PARAMS_OPEN,
    PARAM_NAME,
    PARAM_COLON,
    PARAM_TYPE,
    PARAM_SEP_OR_CLOSE,
    ARROW_OR_BODY,
    RETURN_TYPE,
    EQUALS_OR_REFINEMENT,
    INLINE_BODY,
    REFINEMENT_CLAUSE,
)


# Effect-lattice constraints: for each tier, which effect sigils are legal.
# Tier 0 → empty effect only. Tier 4 may carry any effect.
TIER_LEGAL_EFFECTS: Final[dict[int, frozenset[str]]] = {
    0: frozenset({""}),
    1: frozenset({"", "π"}),
    2: frozenset({"", "π", "σ"}),
    3: frozenset({"", "π", "σ", "ω"}),
    4: frozenset({"", "π", "σ", "ω", "ι", "λ"}),
}

# Type sigils legal in PARAM_TYPE / RETURN_TYPE positions.
LEGAL_TYPE_SIGILS: Final[frozenset[str]] = frozenset({
    "i", "f", "s", "b", "_", "∅",
    # Composite types — mask permits the prefix; expansion is sub-grammar.
    "[", "{", "?",
})


# Tokens that close the current grammar phase (terminators).
PHASE_CLOSERS: Final[dict[str, frozenset[str]]] = {
    PARAMS_OPEN: frozenset({"⟨", ":", "="}),
    PARAM_SEP_OR_CLOSE: frozenset({"⟩"}),
    ARROW_OR_BODY: frozenset({"→", "\n"}),
    EQUALS_OR_REFINEMENT: frozenset({"=", "\n"}),
}
