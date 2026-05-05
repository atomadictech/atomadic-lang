"""Tier a3 — orchestrate corpus collection + BPE training + density measurement.

Walks Python source roots, lowers each Forge-shaped sub-package to .atm
declarations, feeds them into the a2 ``CorpusCollector``, trains a custom
BPE via the a2 ``AtmBpeTrainer``, saves the tokenizer, and reports stats.

Imports a0, a1, a2.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from ..a0_qk_constants.atm_grammar import TIER_DIRS
from ..a0_qk_constants.bpe_config import (
    PYTHON_BASELINE_TOKENIZER,
    TRAINING_CORPUS_SCHEMA_VERSION,
    VOCAB_SIZE,
)
from ..a2_mo_composites.bpe_trainer import AtmBpeTrainer, load_tokenizer
from ..a2_mo_composites.corpus_collector import CorpusCollector
from .lower_feature import lower_package


class TokenizeReport(TypedDict):
    """Output of ``train_atm_tokenizer``."""

    schema_version: str
    corpus_packages: int
    corpus_decls: int
    corpus_chars: int
    corpus_dropped_structural: int
    corpus_dropped_embedded: int
    vocab_size_target: int
    vocab_size_actual: int
    tokenizer_path: str
    sample_atm: str
    sample_atm_token_ids: list[int]
    sample_atm_token_strs: list[str]


def _is_forge_package_root(path: Path) -> bool:
    """A directory is Forge-shaped iff it contains at least one ``aN_*`` subdir."""
    if not path.is_dir():
        return False
    return any((path / t).is_dir() for t in TIER_DIRS)


def _discover_packages(root: Path) -> list[Path]:
    """Return every Forge-shaped package directory at or under ``root``."""
    root = Path(root).resolve()
    if not root.is_dir():
        return []
    if _is_forge_package_root(root):
        return [root]
    seen: set[Path] = set()
    for tier_dir_path in root.rglob("a?_*"):
        if not tier_dir_path.is_dir():
            continue
        if tier_dir_path.name not in TIER_DIRS:
            continue
        pkg_root = tier_dir_path.parent
        if pkg_root in seen:
            continue
        seen.add(pkg_root)
    return sorted(seen)


def collect_corpus(
    source_roots: list[Path],
    *,
    drop_embedded_structural: bool = False,
) -> CorpusCollector:
    """Walk all roots, lower every Forge-shaped sub-package, and return the
    populated ``CorpusCollector``.

    Args:
      source_roots: package roots or parent directories to discover.
      drop_embedded_structural (v2.9): if True, also drop decls whose body
        contains a ``⟪`` structural-fallback brace (catches tier-0 const
        decls polluting the corpus with embedded raw Python).
    """
    collector = CorpusCollector(
        drop_structural=True,
        drop_embedded_structural=drop_embedded_structural,
    )
    seen: set[Path] = set()
    for root in source_roots:
        for pkg_root in _discover_packages(Path(root)):
            if pkg_root in seen:
                continue
            seen.add(pkg_root)
            module = lower_package(pkg_root)
            collector.add_decls(module["decls"], package_count_increment=1)
    return collector


def train_atm_tokenizer(
    *,
    source_roots: list[Path],
    output_tokenizer_path: Path,
    corpus_dump_path: Path | None = None,
    drop_embedded_structural: bool = False,
) -> TokenizeReport:
    """Collect a corpus, train a BPE, save the tokenizer, return a report.

    Args:
      source_roots: package roots or parent directories to discover.
      output_tokenizer_path: where to save the trained tokenizer JSON.
      corpus_dump_path: optional path to also write the raw corpus.
      drop_embedded_structural (v2.9): drop decls whose body contains
        ``⟪`` (raw-Python embedded fallback) before BPE training. This
        is the structural fix for the v2.7/v2.8 overfit finding.
    """
    collector = collect_corpus(
        source_roots,
        drop_embedded_structural=drop_embedded_structural,
    )

    if corpus_dump_path is not None:
        collector.write(Path(corpus_dump_path))

    stats = collector.stats()

    trainer = AtmBpeTrainer()
    trainer.train_from_iterator(collector.lines())

    Path(output_tokenizer_path).parent.mkdir(parents=True, exist_ok=True)
    trainer.save(Path(output_tokenizer_path))

    sample = next(
        (line for line in collector.lines() if line.startswith("1π")),
        collector.lines()[0] if collector.lines() else "",
    )
    sample_ids = trainer.encode(sample) if sample else []
    sample_strs = (
        [trainer.tokenizer.id_to_token(i) for i in sample_ids] if sample else []
    )

    return TokenizeReport(
        schema_version=TRAINING_CORPUS_SCHEMA_VERSION,
        corpus_packages=stats["packages_added"],
        corpus_decls=stats["decls_collected"],
        corpus_chars=stats["total_atm_chars"],
        corpus_dropped_structural=stats["decls_dropped_structural"],
        corpus_dropped_embedded=stats.get("decls_dropped_embedded", 0),
        vocab_size_target=VOCAB_SIZE,
        vocab_size_actual=trainer.vocab_size,
        tokenizer_path=str(Path(output_tokenizer_path).resolve()),
        sample_atm=sample,
        sample_atm_token_ids=sample_ids,
        sample_atm_token_strs=sample_strs,
    )


class DensityReport(TypedDict):
    schema_version: str
    file_path: str
    py_baseline_tokenizer: str
    py_token_count: int
    atm_token_count: int
    density_ratio: float
    char_count_py: int
    char_count_atm: int
    char_density_ratio: float


def measure_density(
    *,
    py_source_path: Path,
    atm_source_path: Path,
    atm_tokenizer_path: Path,
) -> DensityReport:
    """Compare token counts: Python under tiktoken cl100k_base vs .atm under our BPE."""
    py_text = Path(py_source_path).read_text(encoding="utf-8")
    atm_text = Path(atm_source_path).read_text(encoding="utf-8")
    return measure_density_string(
        py_source=py_text,
        atm_source=atm_text,
        atm_tokenizer_path=atm_tokenizer_path,
        file_path=str(Path(atm_source_path).resolve()),
    )


def measure_density_string(
    *,
    py_source: str,
    atm_source: str,
    atm_tokenizer_path: Path,
    file_path: str = "<in-memory>",
) -> DensityReport:
    """In-memory variant of measure_density — used by tests and CLI alike."""
    import tiktoken

    py_enc = tiktoken.get_encoding(PYTHON_BASELINE_TOKENIZER)
    py_tokens = len(py_enc.encode(py_source))

    atm_tok = load_tokenizer(Path(atm_tokenizer_path))
    atm_tokens = len(atm_tok.encode(atm_source).ids)

    return DensityReport(
        schema_version="atomadic-lang.density/v0",
        file_path=file_path,
        py_baseline_tokenizer=PYTHON_BASELINE_TOKENIZER,
        py_token_count=py_tokens,
        atm_token_count=atm_tokens,
        density_ratio=(py_tokens / atm_tokens) if atm_tokens > 0 else 0.0,
        char_count_py=len(py_source),
        char_count_atm=len(atm_source),
        char_density_ratio=(len(py_source) / len(atm_source)) if atm_source else 0.0,
    )


def measure_density_lowered(
    *,
    py_path: Path,
    package: str,
    atm_tokenizer_path: Path,
) -> DensityReport:
    """v2.6 honest density measurement — uses lowerer-emitted .atm, not hand-written.

    The previous pattern (used in early density tests) compared cl100k_base
    on Python source against a hand-curated `.atm` string. That overstates
    density because the hand-curated form is the language at its theoretical
    best, not the lowerer's measured average.

    This function lowers the Python file via the actual `forge lower`
    pipeline and measures density on what the toolchain produces.
    """
    from .lower_feature import lower_file
    from ..a1_at_functions.atm_emit import emit_module

    decls, _py_tokens_via_tokenize = lower_file(Path(py_path), package=package)
    atm_text = emit_module(package, decls)
    py_text = Path(py_path).read_text(encoding="utf-8")
    return measure_density_string(
        py_source=py_text,
        atm_source=atm_text,
        atm_tokenizer_path=atm_tokenizer_path,
        file_path=str(Path(py_path).resolve()),
    )
