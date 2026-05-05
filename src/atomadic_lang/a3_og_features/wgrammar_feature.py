"""Tier a3 — orchestrate W-grammar audit of a trained `.atm` BPE tokenizer.

Loads a tokenizer JSON (saved by ``AtmBpeTrainer.save``), runs the pure a1
``audit_vocab`` over its vocabulary, and produces a serialisable report.

The audit answers: *what fraction of merges learned by this BPE are
W-grammar-structural vs corpus-overfit?* The structural fraction is the
load-bearing predictor of how well density will hold on held-out corpora.

Imports a0, a1, a2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..a1_at_functions.wgrammar_audit import audit_vocab, merges_by_role
from ..a1_at_functions.wgrammar_enforce import (
    DEFAULT_OVERFIT_THRESHOLD,
    evaluate_overfit_bound,
)
from ..a2_mo_composites.bpe_trainer import load_tokenizer


def audit_tokenizer_file(
    tokenizer_path: Path,
    *,
    include_role_listing: bool = False,
) -> dict[str, Any]:
    """Run the W-grammar audit on a saved tokenizer file.

    Args:
      tokenizer_path: path to a HuggingFace ``tokenizers``-format JSON.
      include_role_listing: if True, embed full per-role token listings
        in the output. Defaults to False to keep CLI output compact.

    Returns the audit report (see [a1/wgrammar_audit.audit_vocab][]) with
    ``tokenizer_path`` and (optionally) ``role_listing`` fields added.
    """
    tok = load_tokenizer(Path(tokenizer_path))
    vocab = tok.get_vocab()
    report = audit_vocab(vocab)
    report["tokenizer_path"] = str(Path(tokenizer_path).resolve())
    if include_role_listing:
        report["role_listing"] = merges_by_role(vocab)
    return report


def enforce_tokenizer_file(
    tokenizer_path: Path,
    *,
    threshold: float = DEFAULT_OVERFIT_THRESHOLD,
    include_role_listing: bool = False,
) -> dict[str, Any]:
    """Audit + enforce in one orchestrator call.

    Returns the audit report with an embedded ``enforce`` field carrying
    the verdict produced by ``evaluate_overfit_bound``. The default
    threshold is the anchored ``OVERFIT_BOUND_DEFAULT``.
    """
    report = audit_tokenizer_file(
        tokenizer_path, include_role_listing=include_role_listing
    )
    report["enforce"] = evaluate_overfit_bound(report, threshold=threshold)
    return report


def summarise_audit(report: dict[str, Any]) -> str:
    """Render the audit report as a short human-readable summary."""
    lines = [
        f"W-grammar audit  {report.get('tokenizer_path', '<inline>')}",
        f"  schema:           {report['schema_version']}",
        f"  vocab_size:       {report['vocab_size']}",
        f"  legal_count:      {report['legal_count']}",
        f"  overfit_count:    {report['overfit_count']}",
        f"  overfit_fraction: {report['overfit_fraction']:.3f}",
        "",
        "  role_counts:",
    ]
    # Stable role listing — non-zero rows first, sorted by count desc.
    counts = report["role_counts"]
    nonzero = sorted(
        ((name, n) for name, n in counts.items() if n > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )
    for name, n in nonzero:
        lines.append(f"    {name:20s} {n:5d}")
    if report["overfit_examples"]:
        lines.append("")
        lines.append("  overfit_examples (up to 50):")
        for tok in report["overfit_examples"]:
            lines.append(f"    {tok!r}")
    if "enforce" in report:
        e = report["enforce"]
        lines.append("")
        lines.append("  enforce:")
        lines.append(f"    verdict:          {e['verdict']}")
        lines.append(f"    threshold:        {e['threshold']:.6f} ({e['threshold_source']})")
        lines.append(f"    headroom:         {e['headroom']:+.6f}")
        lines.append(f"    ratio_to_thresh:  {e['ratio_to_threshold']:.2f}x")
    return "\n".join(lines)
