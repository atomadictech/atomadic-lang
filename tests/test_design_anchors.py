"""Tests for tier a0 design_anchors — proves the numerical claims."""

from __future__ import annotations

import math

from atomadic_lang.a0_qk_constants.bpe_config import VOCAB_SIZE
from atomadic_lang.a0_qk_constants.design_anchors import (
    ANCHORED_VOCAB_SIZE,
    DELEGATION_DEPTH_LIMIT,
    HIERARCHY_FACTOR,
    HIERARCHY_FACTOR_DENOMINATOR,
    HIERARCHY_FACTOR_NUMERATOR,
    IDENTITY_RESIDUE,
    KL_DIVERGENCE_BOUND,
    KL_DIVERGENCE_DENOMINATOR,
    KL_DIVERGENCE_NUMERATOR,
    LATTICE_DIMENSION,
    LATTICE_KISSING_NUMBER,
    NUMERIC_TYPE_GENERATIONS,
    OSCILLATOR_PARTITION,
    OVERFIT_BOUND_DEFAULT,
    PRIMARY_MODULAR_COEFF,
    SEMANTIC_FRICTION_DENOMINATOR,
    SEMANTIC_FRICTION_LIMIT,
    SEMANTIC_FRICTION_NUMERATOR,
    TRUST_RATIO,
    TRUST_RATIO_DENOMINATOR,
    TRUST_RATIO_NUMERATOR,
)


# --- Identity residue -----------------------------------------------------


def test_identity_residue_is_exactly_zero() -> None:
    assert IDENTITY_RESIDUE == 0
    assert PRIMARY_MODULAR_COEFF - LATTICE_KISSING_NUMBER - OSCILLATOR_PARTITION == 0


def test_oscillator_partition_equals_eighteen_squared() -> None:
    assert OSCILLATOR_PARTITION == 18 * 18


def test_residue_components_match_anchor_values() -> None:
    assert PRIMARY_MODULAR_COEFF == 196884
    assert LATTICE_KISSING_NUMBER == 196560
    assert OSCILLATOR_PARTITION == 324


# --- Trust ratio ----------------------------------------------------------


def test_trust_ratio_equals_1820_over_1823() -> None:
    assert TRUST_RATIO == TRUST_RATIO_NUMERATOR / TRUST_RATIO_DENOMINATOR
    assert math.isclose(TRUST_RATIO, 0.998354361, abs_tol=1e-6)


def test_trust_ratio_numerator_is_C_16_4() -> None:
    assert TRUST_RATIO_NUMERATOR == math.comb(16, 4)


def test_trust_ratio_denominator_is_prime() -> None:
    assert TRUST_RATIO_DENOMINATOR > 1
    for d in range(2, int(math.isqrt(TRUST_RATIO_DENOMINATOR)) + 1):
        assert TRUST_RATIO_DENOMINATOR % d != 0


def test_trust_ratio_denominator_divides_modular_coeff() -> None:
    assert TRUST_RATIO_DENOMINATOR * 108 == PRIMARY_MODULAR_COEFF


def test_overfit_bound_complements_trust_ratio_to_one() -> None:
    assert math.isclose(
        TRUST_RATIO + OVERFIT_BOUND_DEFAULT, 1.0, abs_tol=1e-12
    )
    assert math.isclose(OVERFIT_BOUND_DEFAULT, 0.001645638, abs_tol=1e-6)


# --- Delegation depth -----------------------------------------------------


def test_delegation_depth_limit_is_23() -> None:
    assert DELEGATION_DEPTH_LIMIT == 23


def test_delegation_depth_derives_from_47_over_eta() -> None:
    eta = 2 * math.cos(math.pi / 30)
    assert math.floor(47 / eta) == DELEGATION_DEPTH_LIMIT


# --- KL divergence bound --------------------------------------------------


def test_kl_divergence_equals_one_over_modular_coeff() -> None:
    assert KL_DIVERGENCE_NUMERATOR == 1
    assert KL_DIVERGENCE_DENOMINATOR == PRIMARY_MODULAR_COEFF
    assert math.isclose(KL_DIVERGENCE_BOUND, 1.0 / 196884, rel_tol=1e-12)


def test_kl_divergence_decimal_value() -> None:
    assert math.isclose(KL_DIVERGENCE_BOUND, 5.07913289e-6, rel_tol=1e-4)


# --- Hierarchy factor -----------------------------------------------------


def test_hierarchy_factor_equals_46_over_43() -> None:
    assert HIERARCHY_FACTOR_NUMERATOR == 46
    assert HIERARCHY_FACTOR_DENOMINATOR == 43
    assert math.isclose(HIERARCHY_FACTOR, 46.0 / 43.0, rel_tol=1e-12)
    assert math.isclose(HIERARCHY_FACTOR, 1.069767, abs_tol=1e-5)


# --- Numeric type generations ---------------------------------------------


def test_numeric_type_generations_equals_three() -> None:
    assert NUMERIC_TYPE_GENERATIONS == 3


# --- Vocabulary size cross-anchor -----------------------------------------


def test_anchored_vocab_size_matches_bpe_config() -> None:
    assert ANCHORED_VOCAB_SIZE == VOCAB_SIZE
    assert ANCHORED_VOCAB_SIZE == 4096


def test_anchored_vocab_size_is_two_to_lattice_dim() -> None:
    assert LATTICE_DIMENSION == 12
    assert ANCHORED_VOCAB_SIZE == 2 ** LATTICE_DIMENSION


# --- Semantic friction limit ----------------------------------------------


def test_semantic_friction_limit_equals_720_over_324() -> None:
    assert SEMANTIC_FRICTION_NUMERATOR == 720
    assert SEMANTIC_FRICTION_DENOMINATOR == 324
    assert math.isclose(
        SEMANTIC_FRICTION_LIMIT, 720.0 / 324.0, rel_tol=1e-12
    )


def test_semantic_friction_denominator_is_18_squared() -> None:
    assert SEMANTIC_FRICTION_DENOMINATOR == 18 * 18


def test_semantic_friction_decimal_value() -> None:
    assert math.isclose(SEMANTIC_FRICTION_LIMIT, 2.222222, abs_tol=1e-5)


def test_semantic_friction_reduces_to_20_over_9() -> None:
    g = math.gcd(SEMANTIC_FRICTION_NUMERATOR, SEMANTIC_FRICTION_DENOMINATOR)
    assert SEMANTIC_FRICTION_NUMERATOR // g == 20
    assert SEMANTIC_FRICTION_DENOMINATOR // g == 9
