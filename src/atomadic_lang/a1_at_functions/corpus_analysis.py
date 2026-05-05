"""Tier a1 — pure corpus analysis for tokenizer signal extraction.

Given a `.atm` corpus (a string or an iterable of lines), surface the
character bigrams and trigrams most worth promoting to forced single
tokens for the BPE. v1.5 uses this for the corpus-driven extension of
``FORCED_SINGLE_TOKENS``.

Imports nothing tier-internal beyond a0 constants.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from ..a0_qk_constants.bpe_config import FORCED_SINGLE_TOKENS, SPECIAL_TOKENS


def char_bigrams(line: str, *, skip_whitespace_boundaries: bool = True) -> Iterable[str]:
    """Yield every character bigram inside ``line``.

    By default skips bigrams that span whitespace (since the HF Whitespace
    pre-tokenizer would split there before BPE merges run).
    """
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        if skip_whitespace_boundaries and (a.isspace() or b.isspace()):
            continue
        yield a + b


def char_trigrams(line: str, *, skip_whitespace_boundaries: bool = True) -> Iterable[str]:
    """Yield every character trigram inside ``line`` that doesn't span whitespace."""
    for i in range(len(line) - 2):
        a, b, c = line[i], line[i + 1], line[i + 2]
        if skip_whitespace_boundaries and any(ch.isspace() for ch in (a, b, c)):
            continue
        yield a + b + c


def count_bigrams(corpus: str | Iterable[str]) -> Counter[str]:
    """Count every cross-line character bigram in the corpus."""
    counter: Counter[str] = Counter()
    if isinstance(corpus, str):
        lines = corpus.splitlines()
    else:
        lines = list(corpus)
    for line in lines:
        counter.update(char_bigrams(line))
    return counter


def count_trigrams(corpus: str | Iterable[str]) -> Counter[str]:
    """Count every cross-line character trigram in the corpus."""
    counter: Counter[str] = Counter()
    if isinstance(corpus, str):
        lines = corpus.splitlines()
    else:
        lines = list(corpus)
    for line in lines:
        counter.update(char_trigrams(line))
    return counter


def is_already_forced(token: str) -> bool:
    """Check whether ``token`` is already in the BPE forced-token list or special tokens."""
    return token in FORCED_SINGLE_TOKENS or token in SPECIAL_TOKENS


def is_structural(token: str) -> bool:
    """Heuristic: a token is "structural" if it's composed of sigils + type letters
    rather than user-domain letters/digits.

    Letters and digits are domain-specific (variable names like ``foo``, numbers like ``42``).
    Operators, brackets, colons, arrows, sigils, and the type-sigil letters
    ``i f s b _`` followed/preceded by structural chars are universally useful.

    The heuristic prefers tokens that are 2+ chars containing at least one
    structural char and no purely-letter prefix that looks domain-specific.
    """
    if not token:
        return False
    structural_chars = set(":→▷⟨⟩⟦⟧⟪⟫=,?|↦@∅+-*/≠≟≤≥∈∉∧∨¬π σ ω ι λ;")
    has_structural = any(c in structural_chars for c in token)
    if not has_structural:
        return False
    # Reject tokens that are mostly word chars with one structural punct.
    # E.g., "self." has 5 word chars + 1 dot — domain-specific (`self` only).
    word_chars = sum(1 for c in token if c.isalnum() or c == "_")
    return word_chars <= 2


def rank_candidates(
    corpus: str | Iterable[str],
    *,
    n_bigrams: int = 30,
    n_trigrams: int = 15,
    min_count: int = 5,
) -> list[tuple[str, int, str]]:
    """Return ranked candidate tokens to add to FORCED_SINGLE_TOKENS.

    Each result is ``(token, count, kind)`` where kind is "bigram" or "trigram".
    Filters: not already forced, structural-shaped, count >= min_count.
    Sorted by count descending.
    """
    bg = count_bigrams(corpus).most_common(n_bigrams * 5)
    tg = count_trigrams(corpus).most_common(n_trigrams * 5)

    candidates: list[tuple[str, int, str]] = []
    for token, count in bg:
        if count < min_count:
            continue
        if is_already_forced(token):
            continue
        if not is_structural(token):
            continue
        candidates.append((token, count, "bigram"))
        if len(candidates) >= n_bigrams:
            break

    trigram_candidates: list[tuple[str, int, str]] = []
    for token, count in tg:
        if count < min_count:
            continue
        if is_already_forced(token):
            continue
        if not is_structural(token):
            continue
        trigram_candidates.append((token, count, "trigram"))
        if len(trigram_candidates) >= n_trigrams:
            break

    candidates.extend(trigram_candidates)
    candidates.sort(key=lambda x: -x[1])
    return candidates
