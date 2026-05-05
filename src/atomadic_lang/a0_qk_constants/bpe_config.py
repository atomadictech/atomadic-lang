"""Tier a0 — BPE tokenizer configuration constants.

Lookup tables only. Zero logic.
"""

from __future__ import annotations

from typing import Final


# Target vocabulary size — locked at 4096 = 2^12.
VOCAB_SIZE: Final[int] = 4096


# Special tokens reserved at the bottom of the vocabulary.
# Order matters — these become token IDs 0..n-1.
SPECIAL_TOKENS: Final[tuple[str, ...]] = (
    "[PAD]",
    "[UNK]",
    "[BOS]",
    "[EOS]",
    "[MASK]",
    "[STRUCTURAL_OPEN]",   # ⟪
    "[STRUCTURAL_CLOSE]",  # ⟫
)


# Sigil characters that should be FORCED as single tokens in the vocabulary.
# These are the .atm structural primitives — they MUST not be split by BPE
# regardless of corpus frequency. v0 list; will grow with the language.
FORCED_SINGLE_TOKENS: Final[tuple[str, ...]] = (
    # tier sigils
    "0", "1", "2", "3", "4",
    # effect sigils
    "π", "σ", "ω", "ι", "λ",
    # tier+effect bigrams (high-frequency openers)
    "0π", "1π", "2σ", "3ω", "4ι", "4λ",
    # type sigils
    "i", "f", "s", "b", "_", "∅",
    # operators / structural
    "→", "▷", "⟨", "⟩", "≠", "≥", "≤", "≟", "∈", "∉", "∧", "∨", "¬",
    "+", "-", "*", "/", "=", ":", ",",
    # module marker
    "@",
    # refinement keywords
    "pre", "post", "body", "enum",
    # v0.8 — comprehension + lambda + f-string sigils
    "↦",        # lambda mapsto: x↦x*2
    "⟦", "⟧",  # f-string substitution brackets: s"hi ⟦name⟧"
    "|",        # comprehension separator: [expr | x ∈ xs]
    "?",        # filter clause: [expr | x ∈ xs ? cond]
    's"',       # f-string-string opener (high-frequency bigram)
    # v1.5 — corpus-driven type-sigil bigrams (per a1/corpus_analysis ranking)
    # Param-position type sigils: ⟨name:T⟩ — every parameter has one
    ":i", ":f", ":s", ":b", ":_", ":∅",
    # Return-type sigils after the arrow
    "→i", "→f", "→s", "→b", "→_", "→∅",
    # List/composite types in params and returns
    ":[s", ":[i", ":[f", ":[_]", "→[_]", "→[s]", "→[i]",
    # Common closing-bracket-arrow combos
    "⟩→", "⟩→i", "⟩→s", "⟩→f", "⟩→_", "⟩→∅",
)


# Pre-tokenizer: how to split source text before BPE merges run.
# We use whitespace pre-tokenization (BoundlessBPE-style merges across
# whitespace are deferred to v1). For .atm this is fine because the
# spec separates declarations by whitespace already.
PRE_TOKENIZER_KIND: Final[str] = "whitespace"


# BPE training corpus paths (filled at training time, not pinned here).
# This is just the manifest schema.
TRAINING_CORPUS_SCHEMA_VERSION: Final[str] = "atomadic-lang.corpus/v0"


# Density-measurement baseline — tiktoken's cl100k_base (GPT-4 tokenizer).
# Used to count Python source for fair comparison with .atm-under-our-BPE.
PYTHON_BASELINE_TOKENIZER: Final[str] = "cl100k_base"
