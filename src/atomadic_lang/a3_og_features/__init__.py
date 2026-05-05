"""Tier a3 — feature orchestrators.

v0   adds ``lower_feature``;
v0.5 adds ``tokenize_feature`` (corpus collect → BPE train + density measurement);
v1.0 adds ``raise_feature`` (parse `.atm` back to LoweredDecl + round-trip).
"""

from .latency_feature import LatencyReport, run_full_benchmark
from .lower_feature import lower_file, lower_package
from .raise_feature import (
    RoundtripReport,
    raise_atm_file,
    raise_atm_text,
    roundtrip_atm_file,
    roundtrip_decls,
)
from .synthetic_corpus import (
    SyntheticPair,
    generate_synthetic_pairs,
    synthetic_corpus_lines,
    synthetic_decls,
)
from .tokenize_feature import (
    DensityReport,
    TokenizeReport,
    measure_density,
    measure_density_lowered,
    measure_density_string,
    train_atm_tokenizer,
)

__all__ = [
    "lower_file",
    "lower_package",
    "DensityReport",
    "TokenizeReport",
    "measure_density",
    "measure_density_lowered",
    "measure_density_string",
    "train_atm_tokenizer",
    "RoundtripReport",
    "raise_atm_file",
    "raise_atm_text",
    "roundtrip_atm_file",
    "roundtrip_decls",
    "LatencyReport",
    "run_full_benchmark",
    "SyntheticPair",
    "generate_synthetic_pairs",
    "synthetic_corpus_lines",
    "synthetic_decls",
]
