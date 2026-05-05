"""Tier a2 — stateful BPE trainer for the .atm v0.5 tokenizer.

Wraps Hugging Face ``tokenizers`` library. Trains a custom BPE on
collected `.atm` corpus with the constraints from REFINED_DESIGN.md §11
(vocab=4096) and the forced-single-token list from a0/bpe_config.

Imports a0 only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import WhitespaceSplit
from tokenizers.trainers import BpeTrainer

from ..a0_qk_constants.bpe_config import (
    FORCED_SINGLE_TOKENS,
    SPECIAL_TOKENS,
    VOCAB_SIZE,
)


class AtmBpeTrainer:
    """Train a custom BPE tokenizer for `.atm` source.

    Configuration is fixed by [bpe_config.py](../a0_qk_constants/bpe_config.py)
    constants. The trainer holds state until ``train`` is called; after
    training the underlying ``Tokenizer`` is exposed via ``tokenizer`` and
    can be saved to disk.
    """

    def __init__(self) -> None:
        self._tokenizer: Tokenizer = Tokenizer(BPE(unk_token="[UNK]"))
        # WhitespaceSplit (split ONLY on whitespace, not on punctuation) lets
        # BPE learn cross-punctuation merges like `:i`, `→i`, `⟩→`. The default
        # Whitespace pre-tokenizer splits on `\w+|[^\w\s]+` which would
        # pre-split `a:i` into three pre-tokens, blocking the type-sigil merges.
        self._tokenizer.pre_tokenizer = WhitespaceSplit()
        self._trainer: BpeTrainer = BpeTrainer(
            vocab_size=VOCAB_SIZE,
            special_tokens=list(SPECIAL_TOKENS),
            initial_alphabet=list(FORCED_SINGLE_TOKENS),
            min_frequency=1,
            show_progress=False,
        )
        self._trained: bool = False

    def train_from_iterator(self, lines: Iterable[str]) -> None:
        """Train the BPE on an iterable of corpus lines."""
        # tokenizers library expects an iterator of strings.
        self._tokenizer.train_from_iterator(list(lines), trainer=self._trainer)
        self._trained = True

    def train_from_text(self, text: str) -> None:
        """Train the BPE on a single text blob (split into lines)."""
        self.train_from_iterator(line for line in text.splitlines() if line.strip())

    def save(self, out_path: Path) -> None:
        """Persist the trained tokenizer to a JSON file."""
        if not self._trained:
            raise RuntimeError("BPE trainer has not been trained yet")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        self._tokenizer.save(str(out_path))

    @property
    def tokenizer(self) -> Tokenizer:
        if not self._trained:
            raise RuntimeError("BPE trainer has not been trained yet")
        return self._tokenizer

    @property
    def vocab_size(self) -> int:
        if not self._trained:
            return 0
        return self._tokenizer.get_vocab_size()

    def encode(self, text: str) -> list[int]:
        """Encode `text` to BPE token IDs."""
        if not self._trained:
            raise RuntimeError("BPE trainer has not been trained yet")
        return self._tokenizer.encode(text).ids

    def decode(self, ids: list[int]) -> str:
        """Decode BPE token IDs back to text."""
        if not self._trained:
            raise RuntimeError("BPE trainer has not been trained yet")
        return self._tokenizer.decode(ids)


def load_tokenizer(path: Path) -> Tokenizer:
    """Load a previously-saved tokenizer from JSON."""
    return Tokenizer.from_file(str(path))
