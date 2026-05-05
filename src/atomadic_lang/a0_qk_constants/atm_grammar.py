"""Tier a0 — sigil tables and tier/effect lookup constants for the .atm v0 surface.

Lookup tables only. Zero logic.
"""

from __future__ import annotations

from typing import Final


# --- Tier sigils ---------------------------------------------------------

# Map directory name → tier digit
TIER_DIRS: Final[dict[str, int]] = {
    "a0_qk_constants": 0,
    "a1_at_functions": 1,
    "a2_mo_composites": 2,
    "a3_og_features": 3,
    "a4_sy_orchestration": 4,
}

# Map tier digit → directory name
TIER_DIGIT_TO_DIR: Final[dict[int, str]] = {v: k for k, v in TIER_DIRS.items()}

# Tier digits we accept in source (must be 0..4)
TIER_DIGITS: Final[tuple[int, ...]] = (0, 1, 2, 3, 4)


# --- Effect sigils -------------------------------------------------------

# Default effect sigil emitted per tier in v0 (no AST inference).
# Tier 0 has no effect sigil (∅).
TIER_DEFAULT_EFFECT_SIGIL: Final[dict[int, str]] = {
    0: "",   # ∅
    1: "π",  # pure
    2: "σ",  # state
    3: "ω",  # orchestrate
    4: "ι",  # io
}

# All known effect sigils (Unicode → ASCII fallback).
EFFECT_SIGIL_TO_ASCII: Final[dict[str, str]] = {
    "π": "p",
    "σ": "s",
    "ω": "o",
    "ι": "i",
    "λ": "l",
}

# Effect sigils ordered by lattice position (low → high).
EFFECT_LATTICE_ORDER: Final[tuple[str, ...]] = ("", "π", "σ", "ω", "ι", "λ")


# --- Type sigils ---------------------------------------------------------

# Python annotation name → .atm type sigil.
PY_TYPE_TO_SIGIL: Final[dict[str, str]] = {
    "int": "i",
    "float": "f",
    "str": "s",
    "bool": "b",
    "bytes": "y",     # speculative; not in spec but reserved
    "None": "∅",
    "Any": "_",
    "object": "_",
}


# --- Operator translation ------------------------------------------------

# Python ast.BinOp class → .atm operator string.
PY_BINOP_TO_ATM: Final[dict[str, str]] = {
    "Add": "+",
    "Sub": "-",
    "Mult": "*",
    "Div": "/",
    "FloorDiv": "//",
    "Mod": "%",
    "Pow": "**",
}

# Python ast.cmpop class → .atm comparison operator string.
PY_CMPOP_TO_ATM: Final[dict[str, str]] = {
    "Eq": "≟",
    "NotEq": "≠",
    "Lt": "<",
    "LtE": "≤",
    "Gt": ">",
    "GtE": "≥",
    "Is": "≟",       # treat as equality at .atm surface in v0
    "IsNot": "≠",
    "In": "∈",
    "NotIn": "∉",
}


# --- Module markers ------------------------------------------------------

PACKAGE_MARKER: Final[str] = "@"
PARAM_OPEN: Final[str] = "⟨"
PARAM_CLOSE: Final[str] = "⟩"
ARROW: Final[str] = "→"
PIPE: Final[str] = "▷"
RAISE: Final[str] = "!"

# Reserved keywords in the v0 surface
RESERVED: Final[frozenset[str]] = frozenset({
    "pre", "post", "body", "enum", "true", "false",
})


# --- Names that get dropped during lowering ------------------------------

# Top-level function names that are infrastructure boilerplate, not logic.
# In v0 we drop docstrings; this set is for explicit ignores.
DROPPED_TOP_LEVEL: Final[frozenset[str]] = frozenset({
    "__init__", "__repr__", "__str__",
})

# v2.7 NOTE (per swarm code-critic, finding #21): DROPPED_IMPORT_MODULES was
# defined here but never imported anywhere. Removed in v2.7. If we later add
# import-dropping logic to lower_feature.py, restore the constant there.
