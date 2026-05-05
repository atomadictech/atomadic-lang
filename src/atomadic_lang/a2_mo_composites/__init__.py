"""Tier a2 — stateful composites.

v0.5 exposes:
- ``CorpusCollector`` — accumulates `.atm` corpus from lowered packages
- ``AtmBpeTrainer`` — trains a custom BPE over the corpus
"""

from .corpus_collector import CorpusCollector
from .bpe_trainer import AtmBpeTrainer, load_tokenizer

__all__ = ["CorpusCollector", "AtmBpeTrainer", "load_tokenizer"]
