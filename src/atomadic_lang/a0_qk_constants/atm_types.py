"""Tier a0 — TypedDicts for the lowered .atm intermediate representation.

These shapes are the wire format between a1 helpers and a3 features.
"""

from __future__ import annotations

from typing import Literal, TypedDict


# Tier digit, narrowed at type-checker level.
TierDigit = Literal[0, 1, 2, 3, 4]

# Effect sigil character (UTF-8) emitted in source.
EffectSigil = Literal["", "π", "σ", "ω", "ι", "λ"]

# Body form emitted for a declaration.
BodyForm = Literal["inline", "refinement", "structural", "class"]


class LoweredParam(TypedDict):
    """One parameter in a function signature."""

    name: str
    type_sigil: str  # e.g. "i", "f", "[i]"


class LoweredDecl(TypedDict):
    """One top-level declaration in a lowered .atm file."""

    tier: TierDigit
    effect: EffectSigil
    name: str
    params: list[LoweredParam]
    return_sigil: str  # "i", "f", "_", "∅", etc.
    body_form: BodyForm
    body: str           # inline expression OR refinement block source OR placeholder
    pre: str            # "" if absent
    post: str           # "" if absent
    source_path: str    # original .py path (relative to package root)
    source_lineno: int  # original lineno (for traceability)


class LoweredModule(TypedDict):
    """A lowered .atm module — one input package."""

    schema_version: str   # "atomadic-lang.lower/v0"
    package: str
    decls: list[LoweredDecl]
    py_token_count: int   # rough Python-side token count for density measurement
    atm_token_count: int  # .atm-side token count for density measurement
    density_ratio: float  # py_token_count / atm_token_count
