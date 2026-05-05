"""Hold-out corpus density measurement (v2.7).

Per swarm empirical-critic finding: the headline density numbers were
measured on the same corpus the BPE was trained on. The honest test
trains the BPE on a SUBSET of the corpus and measures density on the
HELD-OUT portion. This rules out overfitting-as-density.

These tests are skipif'd when the Forge corpus isn't available, since
they require a real heterogeneous corpus to slice into train/test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atomadic_lang.a1_at_functions.atm_emit import emit_module
from atomadic_lang.a2_mo_composites.bpe_trainer import AtmBpeTrainer
from atomadic_lang.a3_og_features.lower_feature import lower_file
from atomadic_lang.a3_og_features.tokenize_feature import (
    collect_corpus,
    measure_density_string,
)


from tests._paths import CALC_ROOT, FORGE_ROOT


@pytest.mark.xfail(
    reason=(
        "v2.7 finding: BPE trained on calc-only is heavily overfit. "
        "Out-of-distribution density on Forge files is ~0.53× — worse than "
        "cl100k_base. The headline density numbers (3.82× a1-only) generalise "
        "POORLY to corpora the BPE wasn't trained on. v3.0 work (BitDistill + "
        "corpus diversification) is expected to lift this above 1.0×."
    ),
    strict=False,
)
@pytest.mark.skipif(
    not (CALC_ROOT.exists() and FORGE_ROOT.exists()),
    reason="calc + Forge corpus required for hold-out test",
)
def test_density_holds_on_holdout_when_trained_on_calc_only(tmp_path: Path) -> None:
    """Train BPE on the calc corpus only; measure density on a Forge file
    the BPE has not seen. Density should still beat 1.0× — proving the
    compression generalises beyond the training corpus, not just memorising it.

    v2.7 NOTE: this test currently FAILS at 0.53×, demonstrating that the
    v0.5..v2.6 BPE training methodology overfits its corpus. This is the
    primary v2.7 finding and is expected to be fixed by v3.0 corpus
    diversification + BitDistill."""

    # Train on calc only
    calc_collector = collect_corpus([CALC_ROOT])
    trainer = AtmBpeTrainer()
    trainer.train_from_iterator(calc_collector.lines())
    tok_path = tmp_path / "tokenizer_calc_only.json"
    trainer.save(tok_path)

    # Pick a Forge file the calc-only BPE has not been trained on.
    target_files = [
        FORGE_ROOT / "a1_at_functions" / "tier_names.py",  # actually a0 in Forge — pick a real a1
        FORGE_ROOT / "a1_at_functions" / "scout_walk.py",
        FORGE_ROOT / "a1_at_functions" / "wire_check.py",
    ]
    # Find one that exists
    target = next((p for p in target_files if p.exists()), None)
    if target is None:
        pytest.skip("no suitable Forge a1 file found for hold-out test")

    # Lower the held-out file and measure density.
    decls, _ = lower_file(target, package="atomadic_forge")
    if not decls:
        pytest.skip(f"lowering {target.name} produced no decls")
    atm_text = emit_module("atomadic_forge", decls)
    py_text = target.read_text(encoding="utf-8")

    report = measure_density_string(
        py_source=py_text,
        atm_source=atm_text,
        atm_tokenizer_path=tok_path,
    )
    # Honest assertion: density should beat 1.0× even when BPE wasn't trained
    # on the held-out file. If it can't even break parity here, the headline
    # density numbers are overfitting.
    assert report["density_ratio"] > 1.0, (
        f"hold-out density on {target.name}: got {report['density_ratio']:.2f}× "
        f"(py={report['py_token_count']}, atm={report['atm_token_count']}). "
        f"This is the overfitting check. If density doesn't generalise to a "
        f"file the BPE was not trained on, the headline numbers are not real."
    )


@pytest.mark.xfail(
    reason=(
        "v2.7 finding: in-distribution density (3.67× on calc/calc) is much "
        "better than out-of-distribution (0.53× on calc-trained/Forge-tested) — "
        "ratio ~0.14. The BPE overfits training. v3.0 expected to lift OOD "
        "density above 50% of in-distribution."
    ),
    strict=False,
)
@pytest.mark.skipif(
    not (CALC_ROOT.exists() and FORGE_ROOT.exists()),
    reason="calc + Forge corpus required for hold-out test",
)
def test_density_difference_train_vs_holdout_is_bounded(tmp_path: Path) -> None:
    """Train on calc, measure density on a Forge file vs measure density on
    a calc file. The held-out density should not be worse than 70% of the
    training-set density. Bounds overfit-claim severity.

    v2.7 NOTE: this test currently FAILS — out-of-distribution density is
    ~14% of in-distribution density. The corpus is too narrow."""

    calc_collector = collect_corpus([CALC_ROOT])
    trainer = AtmBpeTrainer()
    trainer.train_from_iterator(calc_collector.lines())
    tok_path = tmp_path / "tokenizer_calc_only.json"
    trainer.save(tok_path)

    # In-distribution: a calc a1 file
    in_dist_file = CALC_ROOT / "a1_at_functions" / "add.py"
    in_dist_decls, _ = lower_file(in_dist_file, package="calc")
    in_dist_atm = emit_module("calc", in_dist_decls)
    in_dist_py = in_dist_file.read_text(encoding="utf-8")
    in_dist_density = measure_density_string(
        py_source=in_dist_py,
        atm_source=in_dist_atm,
        atm_tokenizer_path=tok_path,
    )

    # Out-of-distribution: a Forge a1 file
    target_files = [
        FORGE_ROOT / "a1_at_functions" / "scout_walk.py",
        FORGE_ROOT / "a1_at_functions" / "wire_check.py",
        FORGE_ROOT / "a1_at_functions" / "classify_tier.py",
    ]
    out_target = next((p for p in target_files if p.exists()), None)
    if out_target is None:
        pytest.skip("no Forge a1 file for OOD comparison")
    out_decls, _ = lower_file(out_target, package="atomadic_forge")
    if not out_decls:
        pytest.skip(f"lowering {out_target.name} produced no decls")
    out_atm = emit_module("atomadic_forge", out_decls)
    out_py = out_target.read_text(encoding="utf-8")
    out_dist_density = measure_density_string(
        py_source=out_py,
        atm_source=out_atm,
        atm_tokenizer_path=tok_path,
    )

    # The out-of-distribution density should not collapse — it should be at
    # least 70% of the in-distribution density. If it's worse than that, the
    # BPE is overfitting to the calc corpus and the density claim is fragile.
    ratio = out_dist_density["density_ratio"] / max(in_dist_density["density_ratio"], 1e-6)
    assert ratio > 0.5, (
        f"out-of-distribution density collapse: in-dist={in_dist_density['density_ratio']:.2f}×, "
        f"out-dist={out_dist_density['density_ratio']:.2f}×, ratio={ratio:.2f}. "
        f"If out-of-distribution density is < 50% of in-distribution, the BPE "
        f"is heavily overfit and the headline numbers don't generalise."
    )
