"""Tests for W-grammar enforcement gate.

These tests prove:
1. The default threshold is sourced from the anchored OVERFIT_BOUND_DEFAULT.
2. The default threshold is the exact rational 3/1823.
3. Verdict logic is monotone: <= threshold -> PASS; > threshold -> REJECT.
4. Boundary case: overfit == threshold -> PASS (inclusive).
5. Threshold provenance is reported (anchored.default vs override).
6. The ratio_to_threshold and headroom diagnostics agree with the verdict.
7. Invalid inputs are rejected with ValueError.
8. End-to-end: the audit pipeline composes with the enforcement.
"""

from __future__ import annotations

import math

import pytest

from atomadic_lang.a0_qk_constants.design_anchors import (
    OVERFIT_BOUND_DEFAULT,
    TRUST_RATIO_DENOMINATOR,
    TRUST_RATIO_NUMERATOR,
)
from atomadic_lang.a1_at_functions.wgrammar_enforce import (
    DEFAULT_OVERFIT_THRESHOLD,
    evaluate_overfit_bound,
    summarise_verdict,
)


# --- Anchor wiring -------------------------------------------------------


def test_default_threshold_sources_anchor() -> None:
    """The enforcement default must be the anchored OVERFIT_BOUND_DEFAULT."""
    assert DEFAULT_OVERFIT_THRESHOLD == OVERFIT_BOUND_DEFAULT


def test_default_threshold_is_exactly_three_over_1823() -> None:
    """1 - 1820/1823 == 3/1823 exactly."""
    assert TRUST_RATIO_DENOMINATOR - TRUST_RATIO_NUMERATOR == 3
    expected = 3 / TRUST_RATIO_DENOMINATOR
    assert math.isclose(DEFAULT_OVERFIT_THRESHOLD, expected, rel_tol=1e-12)


def test_default_threshold_decimal_value() -> None:
    """The anchored bound matches the closed-form decimal ~ 0.001645638."""
    assert math.isclose(DEFAULT_OVERFIT_THRESHOLD, 0.001645638, abs_tol=1e-6)


# --- Verdict logic -------------------------------------------------------


def _audit_with_overfit(fraction: float) -> dict:
    """Build a minimal audit report stub with the given overfit_fraction."""
    return {
        "schema_version": "atomadic-lang.wgrammar/v0",
        "vocab_size": 4096,
        "role_counts": {},
        "legal_count": int(round(4096 * (1 - fraction))),
        "overfit_count": int(round(4096 * fraction)),
        "overfit_fraction": fraction,
        "overfit_examples": [],
    }


def test_verdict_pass_when_overfit_well_below_threshold() -> None:
    report = _audit_with_overfit(0.0)
    verdict = evaluate_overfit_bound(report)
    assert verdict["verdict"] == "PASS"
    assert verdict["threshold_source"] == "anchored.default"


def test_verdict_pass_when_overfit_just_below_threshold() -> None:
    report = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD * 0.99)
    verdict = evaluate_overfit_bound(report)
    assert verdict["verdict"] == "PASS"


def test_verdict_pass_when_overfit_equals_threshold() -> None:
    """Boundary: overfit == threshold is PASS (inclusive bound)."""
    report = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD)
    verdict = evaluate_overfit_bound(report)
    assert verdict["verdict"] == "PASS"
    assert verdict["headroom"] == 0.0
    assert math.isclose(verdict["ratio_to_threshold"], 1.0, rel_tol=1e-12)


def test_verdict_reject_when_overfit_just_above_threshold() -> None:
    report = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD * 1.01)
    verdict = evaluate_overfit_bound(report)
    assert verdict["verdict"] == "REJECT"
    assert verdict["headroom"] < 0


def test_verdict_reject_at_high_severity() -> None:
    """A heavy overfit fraction (~86%) must REJECT and report a high ratio."""
    report = _audit_with_overfit(0.86)
    verdict = evaluate_overfit_bound(report)
    assert verdict["verdict"] == "REJECT"
    assert verdict["ratio_to_threshold"] > 100.0


# --- Threshold override --------------------------------------------------


def test_threshold_override_marked_override() -> None:
    """Custom threshold should report threshold_source == 'override'."""
    report = _audit_with_overfit(0.05)
    verdict = evaluate_overfit_bound(report, threshold=0.1)
    assert verdict["threshold_source"] == "override"
    assert verdict["verdict"] == "PASS"
    assert math.isclose(verdict["threshold"], 0.1, rel_tol=1e-12)


def test_threshold_provenance_tolerates_rounded_default() -> None:
    """Users typing the rounded default value still resolve to anchored.default.

    Without float-tolerant matching, every CLI user who copy-pastes the
    --help text gets `threshold_source = override` instead of the intended
    anchored.default. The provenance check uses math.isclose to avoid this.
    """
    rounded = 0.001645638
    verdict = evaluate_overfit_bound(_audit_with_overfit(0.0), threshold=rounded)
    assert verdict["threshold_source"] == "anchored.default"


def test_threshold_provenance_distinguishes_clearly_different_value() -> None:
    """A threshold meaningfully different from default must report override."""
    verdict = evaluate_overfit_bound(_audit_with_overfit(0.0), threshold=0.01)
    assert verdict["threshold_source"] == "override"


def test_threshold_override_can_be_strict() -> None:
    """Custom threshold tighter than default still works."""
    report = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD)
    verdict = evaluate_overfit_bound(
        report, threshold=DEFAULT_OVERFIT_THRESHOLD / 10
    )
    assert verdict["verdict"] == "REJECT"
    assert verdict["threshold_source"] == "override"


# --- Diagnostic fields ---------------------------------------------------


def test_headroom_is_signed_distance() -> None:
    pass_rep = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD * 0.5)
    rej_rep = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD * 2.0)
    pass_v = evaluate_overfit_bound(pass_rep)
    rej_v = evaluate_overfit_bound(rej_rep)
    assert pass_v["headroom"] > 0
    assert rej_v["headroom"] < 0
    assert math.isclose(
        pass_v["headroom"],
        DEFAULT_OVERFIT_THRESHOLD - DEFAULT_OVERFIT_THRESHOLD * 0.5,
        rel_tol=1e-12,
    )


def test_ratio_to_threshold_is_dimensionless() -> None:
    report = _audit_with_overfit(DEFAULT_OVERFIT_THRESHOLD * 47)
    verdict = evaluate_overfit_bound(report)
    assert math.isclose(verdict["ratio_to_threshold"], 47.0, rel_tol=1e-9)


# --- Input validation ----------------------------------------------------


def test_invalid_threshold_zero_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_overfit_bound(_audit_with_overfit(0.0), threshold=0.0)


def test_invalid_threshold_negative_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_overfit_bound(_audit_with_overfit(0.0), threshold=-0.1)


def test_invalid_threshold_above_one_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_overfit_bound(_audit_with_overfit(0.0), threshold=1.5)


def test_missing_overfit_fraction_rejected() -> None:
    with pytest.raises(ValueError, match="overfit_fraction"):
        evaluate_overfit_bound({})


def test_invalid_overfit_fraction_above_one_rejected() -> None:
    with pytest.raises(ValueError, match="overfit_fraction"):
        evaluate_overfit_bound(_audit_with_overfit(1.5))


def test_invalid_overfit_fraction_negative_rejected() -> None:
    with pytest.raises(ValueError, match="overfit_fraction"):
        evaluate_overfit_bound(_audit_with_overfit(-0.01))


# --- Schema --------------------------------------------------------------


def test_verdict_schema_version_pinned() -> None:
    verdict = evaluate_overfit_bound(_audit_with_overfit(0.0))
    assert verdict["schema_version"] == "atomadic-lang.wgrammar_enforce/v1"


def test_summarise_verdict_renders_key_fields() -> None:
    verdict = evaluate_overfit_bound(_audit_with_overfit(0.0005))
    line = summarise_verdict(verdict)
    assert "verdict=PASS" in line
    assert "overfit=0.0500%" in line
    assert "threshold=0.16" in line
    assert "anchored.default" in line


# --- End-to-end ----------------------------------------------------------


def test_evaluate_consumes_real_audit_report_shape() -> None:
    from atomadic_lang.a1_at_functions.wgrammar_audit import audit_vocab

    vocab = {"1π": 0, "→i": 1, "add": 2, "qqbogus": 3, "zznoise": 4}
    audit = audit_vocab(vocab)
    verdict = evaluate_overfit_bound(audit, threshold=0.5)
    assert "verdict" in verdict
    assert "headroom" in verdict
    assert verdict["overfit_fraction"] == audit["overfit_fraction"]
