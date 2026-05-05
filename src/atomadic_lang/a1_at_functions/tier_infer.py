"""Tier a1 — pure tier inference from a file path.

Given a Forge-organized Python file path, return the tier digit.
"""

from __future__ import annotations

from pathlib import Path

from ..a0_qk_constants.atm_grammar import (
    TIER_DEFAULT_EFFECT_SIGIL,
    TIER_DIRS,
    TIER_DIGITS,
)


def tier_from_path(path: Path) -> int:
    """Return the tier digit (0..4) for a Forge-organized .py file.

    Looks for an ``aN_*`` directory anywhere in the path components.
    Raises ``ValueError`` if no recognised tier dir is found.
    """
    parts = Path(path).parts
    for part in parts:
        if part in TIER_DIRS:
            return TIER_DIRS[part]
    raise ValueError(
        f"path {path!s} does not lie under a recognised tier directory "
        f"(expected one of: {sorted(TIER_DIRS)})"
    )


def effect_for_tier(tier: int) -> str:
    """Return the v0-default effect sigil for the given tier.

    v0 does NOT infer effects from AST — it uses the tier-default sigil.
    Future versions (v0.5+) will analyse the function body.
    """
    if tier not in TIER_DIGITS:
        raise ValueError(f"tier must be in {TIER_DIGITS}, got {tier!r}")
    return TIER_DEFAULT_EFFECT_SIGIL[tier]


def package_from_path(path: Path) -> str:
    """Extract the package name from a Forge-organized .py file path.

    Example: ``src/calc/a1_at_functions/add.py`` → ``"calc"``.
    Looks for the directory immediately before any ``aN_*`` directory.
    """
    parts = Path(path).parts
    for i, part in enumerate(parts):
        if part in TIER_DIRS:
            if i == 0:
                raise ValueError(f"no package directory above tier dir in {path!s}")
            return parts[i - 1]
    raise ValueError(
        f"path {path!s} does not lie under a recognised tier directory"
    )
