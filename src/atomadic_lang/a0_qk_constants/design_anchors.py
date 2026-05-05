"""Tier a0 — numerical anchors used as gate thresholds and verification bounds.

Lookup tables only. Zero logic.
"""

from __future__ import annotations

from typing import Final


# --- Identity-residue invariant -------------------------------------------
# Three known integer constants from public moonshine / lattice literature
# that algebraically cancel: A - B - C = 0. Used as the conceptual anchor
# for the round-trip identity property of the IR (parse o emit = id;
# every byte accounted for).

PRIMARY_MODULAR_COEFF: Final[int] = 196884
LATTICE_KISSING_NUMBER: Final[int] = 196560
OSCILLATOR_PARTITION: Final[int] = 324
IDENTITY_RESIDUE: Final[int] = (
    PRIMARY_MODULAR_COEFF - LATTICE_KISSING_NUMBER - OSCILLATOR_PARTITION
)


# --- Trust-ratio threshold ------------------------------------------------
# Trust threshold for "ship the IR" — used by the W-grammar enforcement
# gate. Numerator is the binomial C(16, 4); denominator is a safe prime
# adjacent to the modular coefficient.

TRUST_RATIO_NUMERATOR: Final[int] = 1820
TRUST_RATIO_DENOMINATOR: Final[int] = 1823
TRUST_RATIO: Final[float] = TRUST_RATIO_NUMERATOR / TRUST_RATIO_DENOMINATOR
OVERFIT_BOUND_DEFAULT: Final[float] = 1.0 - TRUST_RATIO


# --- Delegation-depth limit -----------------------------------------------
# Bounds recursion depth for the lowering / parser / refinement stacks.

DELEGATION_DEPTH_LIMIT: Final[int] = 23


# --- KL-divergence bound on corpus drift ----------------------------------
# Bounds the acceptable density drift between training and held-out
# corpora.

KL_DIVERGENCE_NUMERATOR: Final[int] = 1
KL_DIVERGENCE_DENOMINATOR: Final[int] = 196884
KL_DIVERGENCE_BOUND: Final[float] = (
    KL_DIVERGENCE_NUMERATOR / KL_DIVERGENCE_DENOMINATOR
)


# --- Hierarchy factor -----------------------------------------------------
# Coverage ratio between adjacent tier blocks.

HIERARCHY_FACTOR_NUMERATOR: Final[int] = 46
HIERARCHY_FACTOR_DENOMINATOR: Final[int] = 43
HIERARCHY_FACTOR: Final[float] = (
    HIERARCHY_FACTOR_NUMERATOR / HIERARCHY_FACTOR_DENOMINATOR
)


# --- Numeric type generation count ----------------------------------------
# Mirrors the 3 primitive numeric type sigils in the .atm type lattice.

NUMERIC_TYPE_GENERATIONS: Final[int] = 3


# --- Vocabulary size anchor -----------------------------------------------
# Mirrors bpe_config.VOCAB_SIZE = 2^12 = 4096 (structured GF(2^12) IDs).

ANCHORED_VOCAB_SIZE: Final[int] = 4096
LATTICE_DIMENSION: Final[int] = 12


# --- Semantic friction limit ----------------------------------------------
# Ceiling for the IR's character-density compression vs reference source.
# A measured density at fraction F of the limit means the IR has reached
# F * 100% of the compression budget; pushing further trades legibility
# for density.

SEMANTIC_FRICTION_NUMERATOR: Final[int] = 720
SEMANTIC_FRICTION_DENOMINATOR: Final[int] = 324
SEMANTIC_FRICTION_LIMIT: Final[float] = (
    SEMANTIC_FRICTION_NUMERATOR / SEMANTIC_FRICTION_DENOMINATOR
)
