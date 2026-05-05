"""Tier a1 — pure W-grammar enforcement gate.

Companion to ``wgrammar_audit``. The audit classifies BPE merges; this
module turns the classification into a binding gate by comparing
``overfit_fraction`` against an anchored threshold.

The default threshold is the design-anchored ``OVERFIT_BOUND_DEFAULT``
( = 3 / 1823 ~= 0.001646). Values <= the bound imply the BPE has at most
a small fraction of corpus-overfit merges; values above imply density
will not generalise across corpora.

Pure stateless functions only. Imports a0 only.
"""

from __future__ import annotations

import math
from typing import Any, Final, Literal

from ..a0_qk_constants.design_anchors import OVERFIT_BOUND_DEFAULT


EnforceVerdict = Literal["PASS", "REJECT"]


DEFAULT_OVERFIT_THRESHOLD: Final[float] = OVERFIT_BOUND_DEFAULT


def evaluate_overfit_bound(
    audit_report: dict[str, Any],
    threshold: float = DEFAULT_OVERFIT_THRESHOLD,
) -> dict[str, Any]:
    """Compare an audit report's overfit_fraction against a threshold.

    Args:
      audit_report: a report produced by ``audit_vocab`` — must contain
        ``overfit_fraction`` (float in [0, 1]).
      threshold: the maximum acceptable overfit fraction. Defaults to
        the anchored ``OVERFIT_BOUND_DEFAULT`` (~ 0.001645638).

    Returns a JSON-serialisable verdict dict with:
      - ``schema_version``: report schema id
      - ``verdict``: ``"PASS"`` if ``overfit_fraction <= threshold``,
        else ``"REJECT"``
      - ``threshold``: the threshold used for the comparison
      - ``threshold_source``: ``"anchored.default"`` if the default was
        used, else ``"override"``
      - ``overfit_fraction``: the measured value from the audit
      - ``headroom``: ``threshold - overfit_fraction``
      - ``ratio_to_threshold``: ``overfit_fraction / threshold``

    Raises:
      ValueError: if the audit_report is missing ``overfit_fraction`` or
        the value is not in [0, 1], or threshold not in (0, 1].
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(
            f"threshold must be in (0, 1]; got {threshold!r}"
        )

    if "overfit_fraction" not in audit_report:
        raise ValueError(
            "audit_report missing required key 'overfit_fraction' "
            "(was the report produced by audit_vocab?)"
        )

    overfit = audit_report["overfit_fraction"]
    if not isinstance(overfit, (int, float)) or not 0.0 <= overfit <= 1.0:
        raise ValueError(
            f"overfit_fraction must be a float in [0, 1]; got {overfit!r}"
        )

    verdict: EnforceVerdict = "PASS" if overfit <= threshold else "REJECT"
    threshold_source = (
        "anchored.default"
        if math.isclose(
            threshold, DEFAULT_OVERFIT_THRESHOLD, rel_tol=1e-6, abs_tol=1e-9
        )
        else "override"
    )

    return {
        "schema_version": "atomadic-lang.wgrammar_enforce/v1",
        "verdict": verdict,
        "threshold": threshold,
        "threshold_source": threshold_source,
        "overfit_fraction": float(overfit),
        "headroom": float(threshold - overfit),
        "ratio_to_threshold": (
            float(overfit) / threshold if threshold > 0 else float("inf")
        ),
    }


def summarise_verdict(verdict_report: dict[str, Any]) -> str:
    """Render an enforcement verdict as a short human-readable line."""
    overfit_pct = verdict_report["overfit_fraction"] * 100
    threshold_pct = verdict_report["threshold"] * 100
    ratio = verdict_report["ratio_to_threshold"]
    return (
        f"W-grammar enforce  verdict={verdict_report['verdict']}  "
        f"overfit={overfit_pct:.4f}%  "
        f"threshold={threshold_pct:.4f}% ({verdict_report['threshold_source']})  "
        f"ratio={ratio:.2f}x"
    )
