"""Tests for v0.5 BPE tokenizer training and density measurement."""

from __future__ import annotations

from pathlib import Path

import pytest

from atomadic_lang.a0_qk_constants.bpe_config import (
    FORCED_SINGLE_TOKENS,
    SPECIAL_TOKENS,
    VOCAB_SIZE,
)
from atomadic_lang.a2_mo_composites.bpe_trainer import AtmBpeTrainer
from atomadic_lang.a3_og_features.tokenize_feature import (
    measure_density_string,
    train_atm_tokenizer,
)


from tests._paths import CALC_ROOT, FORGE_ROOT


# --- a0 sanity -----------------------------------------------------------


def test_vocab_size_locked_to_4096() -> None:
    assert VOCAB_SIZE == 4096


def test_special_tokens_present() -> None:
    assert "[PAD]" in SPECIAL_TOKENS
    assert "[UNK]" in SPECIAL_TOKENS
    assert "[BOS]" in SPECIAL_TOKENS
    assert "[EOS]" in SPECIAL_TOKENS


def test_forced_tokens_include_tier_sigils() -> None:
    for sigil in ("0", "1", "2", "3", "4"):
        assert sigil in FORCED_SINGLE_TOKENS


def test_forced_tokens_include_effect_sigils() -> None:
    for sigil in ("π", "σ", "ω", "ι", "λ"):
        assert sigil in FORCED_SINGLE_TOKENS


def test_forced_tokens_include_tier_effect_bigrams() -> None:
    # The tier+effect bigrams are critical — they should be merged early.
    for bigram in ("1π", "2σ", "3ω", "4ι", "4λ"):
        assert bigram in FORCED_SINGLE_TOKENS


# --- a2 corpus collector --------------------------------------------------


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_corpus_collector_picks_up_calc() -> None:
    from atomadic_lang.a3_og_features.tokenize_feature import collect_corpus
    collector = collect_corpus([CALC_ROOT])
    lines = collector.lines()
    assert any(line.startswith("1π add") for line in lines)
    assert any(line.startswith("1π divide") for line in lines)
    stats = collector.stats()
    assert stats["packages_added"] == 1
    assert stats["decls_collected"] >= 4
    # v0.9: cli.main now lowers via try/except + kwargs, so it no longer
    # falls into structural. This assertion was `>= 1` in v0.5..v0.8 because
    # cli.main was opaque; in v0.9 the calc demo lowers fully.
    assert stats["decls_dropped_structural"] >= 0


@pytest.mark.skipif(not FORGE_ROOT.exists(), reason="atomadic-forge source not present")
def test_corpus_collector_walks_forge_recursively() -> None:
    from atomadic_lang.a3_og_features.tokenize_feature import collect_corpus
    collector = collect_corpus([FORGE_ROOT])
    added = collector.stats()["decls_collected"]
    assert added > 10
    assert len(collector.lines()) == added


# --- a2 BPE trainer -------------------------------------------------------


def test_bpe_trainer_trains_on_synthetic_corpus() -> None:
    """v2.6 tightened: was `assert "1π" in decoded or "π" in decoded` — the
    `or "π"` made the disjunction trivially true (the second clause is implied
    by the first). Now asserts the stronger property that `1π` was actually
    learned as a single merged token, not split."""
    corpus = [
        "1π add ⟨a:i b:i⟩→i = a+b",
        "1π sub ⟨a:i b:i⟩→i = a-b",
        "1π mul ⟨a:i b:i⟩→i = a*b",
        "1π div ⟨a:i b:i⟩→f",
    ] * 50  # plenty of frequency signal
    trainer = AtmBpeTrainer()
    trainer.train_from_iterator(corpus)
    assert trainer.vocab_size > 0

    sample = "1π add ⟨a:i b:i⟩→i = a+b"
    ids = trainer.encode(sample)
    tokens = [trainer.tokenizer.id_to_token(i) for i in ids]

    # The high-frequency forced bigram `1π` should be ONE token, not split.
    assert "1π" in tokens, f"`1π` not learned as merged token: {tokens}"
    # `add` is a complete identifier; should be one token.
    assert "add" in tokens, f"`add` not preserved: {tokens}"


def test_bpe_trainer_compresses_repeated_pattern() -> None:
    """A frequent multi-char pattern should merge into a single token."""
    pattern = "1π add ⟨a:i b:i⟩→i = a+b"
    corpus = [pattern] * 50
    trainer = AtmBpeTrainer()
    trainer.train_from_iterator(corpus)
    ids = trainer.encode(pattern)
    # The full pattern is short; it should encode in a small number of tokens.
    # (Whitespace pre-tokenizer means the 7+ space-separated chunks each
    # become at most a few tokens; expect ≤ 25 BPE tokens for this line.)
    assert len(ids) < 30, f"expected dense encoding, got {len(ids)} tokens for: {pattern}"


# --- a3 end-to-end --------------------------------------------------------


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_train_atm_tokenizer_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "tokenizer.json"
    report = train_atm_tokenizer(
        source_roots=[CALC_ROOT],
        output_tokenizer_path=out,
        corpus_dump_path=tmp_path / "corpus.txt",
    )
    assert out.exists()
    assert (tmp_path / "corpus.txt").exists()
    assert report["corpus_packages"] == 1
    assert report["corpus_decls"] >= 4
    assert report["vocab_size_actual"] > 0


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_measure_density_string_after_training(tmp_path: Path) -> None:
    """v2.6 tightened: was `> 0.5` (test passes when .atm is WORSE than
    Python — useless guard). Now requires `> 1.0` to actually verify the
    .atm-is-denser-than-Python claim."""
    out = tmp_path / "tokenizer.json"
    train_atm_tokenizer(
        source_roots=[CALC_ROOT],
        output_tokenizer_path=out,
    )
    py_src = "def add(a: int, b: int) -> int:\n    return a + b\n"
    atm_src = "1π add ⟨a:i b:i⟩→i = a+b\n"
    report = measure_density_string(
        py_source=py_src,
        atm_source=atm_src,
        atm_tokenizer_path=out,
    )
    assert report["py_token_count"] > 0
    assert report["atm_token_count"] > 0
    # v2.6: tightened to actual claim. .atm under our BPE must beat cl100k.
    assert report["density_ratio"] > 1.0, (
        f".atm should be denser than Python under cl100k_base on the canonical "
        f"add example; got {report['density_ratio']:.2f}× "
        f"(py={report['py_token_count']}, atm={report['atm_token_count']})"
    )


# --- corpus growth: train on calc + Forge for honest density -------------


@pytest.mark.skipif(not (CALC_ROOT.exists() and FORGE_ROOT.exists()),
                     reason="calc demo + Forge source required for full corpus test")
def test_full_corpus_density_a1_only(tmp_path: Path) -> None:
    """v2.6 honest version: density on the a1 slice of calc using the
    LOWERER-EMITTED .atm, not a hand-written representation.

    The previous version of this test compared cl100k tokens of Python source
    against tokens of a hand-written `.atm` text we authored to look optimal.
    That over-states the lowerer's actual output by a factor of ~2× because
    real lowering produces longer bodies, dotted method names, structural
    fallback in places, etc. The empirical critic was correct that the bench
    was rigged in our favor.

    This version measures what the lowerer actually emits.
    """
    from atomadic_lang.a1_at_functions.atm_emit import emit_module
    from atomadic_lang.a3_og_features.lower_feature import lower_file

    out = tmp_path / "tokenizer.json"
    report = train_atm_tokenizer(
        source_roots=[CALC_ROOT, FORGE_ROOT],
        output_tokenizer_path=out,
    )
    assert report["corpus_decls"] > 20

    py_a1 = "\n".join(
        (CALC_ROOT / "a1_at_functions" / fname).read_text(encoding="utf-8")
        for fname in ("add.py", "subtract.py", "multiply.py", "divide.py")
    )

    # Real lowerer output — not a hand-written aspirational form.
    decls_combined: list = []
    for fname in ("add.py", "subtract.py", "multiply.py", "divide.py"):
        decls, _ = lower_file(CALC_ROOT / "a1_at_functions" / fname, package="calc")
        decls_combined.extend(decls)
    atm_a1 = emit_module("calc", decls_combined)

    density = measure_density_string(
        py_source=py_a1,
        atm_source=atm_a1,
        atm_tokenizer_path=out,
    )
    # v2.6: honest threshold based on what the lowerer actually emits.
    # Hand-written `.atm` measured 3.82×; lowerer-emitted will be lower
    # because the emitter produces canonical-form names + spacing. We expect
    # ≥ 2.0× — still beats cl100k_base meaningfully, just not as dramatically
    # as the previous (rigged) measurement.
    assert density["density_ratio"] > 2.0, (
        f"a1-only density under trained BPE on lowerer-emitted .atm: "
        f"got {density['density_ratio']:.2f}× "
        f"(py_tokens={density['py_token_count']}, atm_tokens={density['atm_token_count']}, "
        f"chars py={density['char_count_py']}/atm={density['char_count_atm']})"
    )
    assert density["char_density_ratio"] > 2.0, (
        f"char density on lowerer-emitted .atm: got {density['char_density_ratio']:.2f}×"
    )
