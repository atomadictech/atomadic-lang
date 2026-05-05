"""Tests for v2.0 §1 latency benchmark components."""

from __future__ import annotations

from pathlib import Path

import pytest

from atomadic_lang.a0_qk_constants.bpe_config import VOCAB_SIZE
from atomadic_lang.a0_qk_constants.grammar_states import (
    DECL_NAME,
    DECL_START,
    INLINE_BODY,
    TIER_LEGAL_EFFECTS,
)
from atomadic_lang.a1_at_functions.mask_evaluator import (
    MASK_BYTES,
    all_mask,
    empty_mask,
    is_permitted,
    precompute_phase_masks,
    set_token,
    transition,
)
from atomadic_lang.a1_at_functions.refinement_eval import (
    compile_predicate,
    eval_eq_zero,
    eval_in_set,
    eval_len_gt_zero,
    eval_lt_const,
)


TOKENIZER_V15 = Path(__file__).resolve().parent.parent / "tokenizer_v15.json"


# --- a0 grammar states ---------------------------------------------------


def test_tier_legal_effects() -> None:
    """Tier-0 has only the empty effect; tier-4 has every effect."""
    assert TIER_LEGAL_EFFECTS[0] == frozenset({""})
    assert "λ" in TIER_LEGAL_EFFECTS[4]
    assert "ι" in TIER_LEGAL_EFFECTS[4]
    assert "λ" not in TIER_LEGAL_EFFECTS[3]


# --- a1 mask helpers -----------------------------------------------------


def test_empty_mask_is_zeros() -> None:
    m = empty_mask()
    assert len(m) == MASK_BYTES
    assert all(b == 0 for b in m)


def test_all_mask_is_ones() -> None:
    m = all_mask()
    assert len(m) == MASK_BYTES
    assert all(b == 0xFF for b in m)


def test_set_token_round_trip() -> None:
    m = empty_mask()
    set_token(m, 42)
    assert is_permitted(m, 42)
    assert not is_permitted(m, 41)


def test_mask_bytes_match_vocab() -> None:
    """4096-token vocab → 512 bytes of mask (8 tokens per byte)."""
    assert MASK_BYTES * 8 == VOCAB_SIZE


# --- a1 transition function ----------------------------------------------


def test_transition_module_start_to_decl_start_on_at() -> None:
    new_state = transition("MODULE_START", "@calc")
    assert new_state == DECL_START


def test_transition_decl_start_to_decl_name_on_tier() -> None:
    new_state = transition(DECL_START, "1π")
    assert new_state == DECL_NAME


def test_transition_decl_name_to_inline_body_on_equals() -> None:
    new_state = transition(DECL_NAME, "=")
    assert new_state == INLINE_BODY


# --- a1 refinement evaluator ---------------------------------------------


def test_compile_predicate_simple_neq() -> None:
    pred = compile_predicate("b≠0")
    assert pred({"b": 5}) is True
    assert pred({"b": 0}) is False


def test_compile_predicate_length() -> None:
    pred = compile_predicate("|xs|>0")
    assert pred({"xs": [1, 2]}) is True
    assert pred({"xs": []}) is False


def test_compile_predicate_conjunction() -> None:
    pred = compile_predicate("b≠0 ∧ a>0")
    assert pred({"a": 1, "b": 1}) is True
    assert pred({"a": 1, "b": 0}) is False
    assert pred({"a": 0, "b": 1}) is False


def test_compile_predicate_membership() -> None:
    pred = compile_predicate("op∈{1,2,3}")
    assert pred({"op": 2}) is True
    assert pred({"op": 4}) is False


def test_eval_eq_zero_inline() -> None:
    assert eval_eq_zero(5) is True
    assert eval_eq_zero(0) is False


def test_eval_lt_const_inline() -> None:
    assert eval_lt_const(5, 23) is True
    assert eval_lt_const(23, 23) is False


def test_eval_len_gt_zero_inline() -> None:
    assert eval_len_gt_zero([1, 2]) is True
    assert eval_len_gt_zero([]) is False


def test_eval_in_set_inline() -> None:
    assert eval_in_set("+", ("+", "-", "*")) is True
    assert eval_in_set("%", ("+", "-", "*")) is False


# --- a3 benchmark sanity -------------------------------------------------


@pytest.mark.skipif(not TOKENIZER_V15.exists(), reason="v1.5 tokenizer not present")
def test_benchmark_returns_valid_report() -> None:
    from atomadic_lang.a3_og_features.latency_feature import run_full_benchmark

    report = run_full_benchmark(
        tokenizer_path=TOKENIZER_V15,
        iters_fast=1_000,   # fast iters for the test
        iters_e2e=10,
    )
    # Schema is what we expect.
    assert report["schema_version"] == "atomadic-lang.latency/v0"
    assert report["target_budget_us"] == 50.0
    # All four component stats are populated.
    for key in ("mask_application_ns", "state_transition_ns",
                "refinement_compiled_ns", "end_to_end_ns"):
        stats = report[key]
        assert "median" in stats
        assert "p95" in stats
        assert stats["p95"] >= 0
    # Verdict is one of the three expected prefixes.
    assert report["verdict"].startswith(("PASS", "REFINE", "FAIL"))


@pytest.mark.skipif(not TOKENIZER_V15.exists(), reason="v1.5 tokenizer not present")
def test_phase_mask_precompute() -> None:
    """All phase masks should be 512-byte bitmaps; lookup is O(1)."""
    from atomadic_lang.a2_mo_composites.bpe_trainer import load_tokenizer

    tok = load_tokenizer(TOKENIZER_V15)
    vocab = tok.get_vocab()
    masks = precompute_phase_masks(vocab)
    # Every state has a precomputed mask of exactly MASK_BYTES.
    for phase, mask in masks.items():
        assert len(mask) == MASK_BYTES, f"phase {phase} has wrong mask size"
    # MODULE_START should permit `@`-prefixed tokens.
    at_token_ids = [tid for tok, tid in vocab.items() if tok.startswith("@")]
    if at_token_ids:
        any_permitted = any(
            is_permitted(masks["MODULE_START"], tid) for tid in at_token_ids
        )
        assert any_permitted, "MODULE_START mask doesn't permit `@`-prefixed tokens"
