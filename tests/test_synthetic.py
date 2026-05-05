"""Tests for v2.5 synthetic corpus generator."""

from __future__ import annotations

from atomadic_lang.a3_og_features.synthetic_corpus import (
    generate_synthetic_pairs,
    synthetic_corpus_lines,
    synthetic_decls,
)


def test_generate_basic() -> None:
    pairs = generate_synthetic_pairs(n=10, seed=123)
    assert len(pairs) == 10
    for p in pairs:
        assert p["nl"]
        assert p["atm_line"]
        assert p["decl"]["name"]


def test_seed_determinism() -> None:
    a = generate_synthetic_pairs(n=20, seed=42)
    b = generate_synthetic_pairs(n=20, seed=42)
    assert a == b


def test_generated_atm_lines_have_tier_sigil() -> None:
    pairs = generate_synthetic_pairs(n=50, seed=7)
    for p in pairs:
        # Every line should start with a tier digit.
        assert p["atm_line"][0] in "01234"


def test_arithmetic_pairs_have_two_int_params() -> None:
    pairs = generate_synthetic_pairs(n=200, seed=1, weights={"arith": 1.0})
    for p in pairs:
        decl = p["decl"]
        assert decl["tier"] == 1
        assert decl["effect"] == "π"
        assert len(decl["params"]) == 2


def test_record_pairs_emit_class_form() -> None:
    pairs = generate_synthetic_pairs(n=50, seed=2, weights={"record": 1.0})
    for p in pairs:
        assert p["decl"]["tier"] == 0
        assert p["decl"]["body_form"] == "class"
        assert p["decl"]["body"] == ""


def test_refinement_pairs_have_pre_clause() -> None:
    pairs = generate_synthetic_pairs(n=50, seed=3, weights={"refinement": 1.0})
    for p in pairs:
        assert p["decl"]["body_form"] == "refinement"
        assert p["decl"]["pre"]


def test_corpus_lines_extraction() -> None:
    pairs = generate_synthetic_pairs(n=15, seed=4)
    lines = synthetic_corpus_lines(pairs)
    assert len(lines) == 15
    assert all(isinstance(line, str) for line in lines)


def test_decls_extraction_matches_pairs() -> None:
    pairs = generate_synthetic_pairs(n=15, seed=5)
    decls = synthetic_decls(pairs)
    assert len(decls) == 15
    for pair, decl in zip(pairs, decls):
        assert decl == pair["decl"]


def test_5000_pairs_unique_enough() -> None:
    """Generating 5000 pairs should give us at least 50 unique line shapes
    (template-based, but parameterized by names + ops)."""
    pairs = generate_synthetic_pairs(n=5000, seed=9)
    unique_lines = {p["atm_line"] for p in pairs}
    assert len(unique_lines) > 50, f"only {len(unique_lines)} unique lines"


def test_balanced_kind_distribution() -> None:
    """Default mix should produce all 5 kinds when n is large enough."""
    pairs = generate_synthetic_pairs(n=2000, seed=11)
    tiers = [p["decl"]["tier"] for p in pairs]
    body_forms = [p["decl"]["body_form"] for p in pairs]
    assert 0 in tiers and 1 in tiers
    assert "inline" in body_forms
    assert "class" in body_forms
    assert "refinement" in body_forms
