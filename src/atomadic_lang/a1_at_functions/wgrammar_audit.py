"""Tier a1 — pure W-grammar (Van Wijngaarden) merge auditor for `.atm` BPE.

Implements breakthrough B-016 (W-grammar BPE merge filter): given any
trained BPE vocabulary, classify every emitted token by its structural
role in the .atm surface grammar. Tokens that fail to classify into a
known role are flagged as **overfit** — i.e., the BPE learned a
corpus-frequency merge that does not respect the language's structural
bigram set, so it will not generalise to held-out corpora.

This is the structural countermeasure to the v2.7 hold-out density
finding (in-distribution 3.67× vs out-of-distribution 0.53×, ratio 0.14).
A high overfit-merge fraction is a leading indicator of poor density
generalisation.

Pure stateless functions only. Imports a0 only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from ..a0_qk_constants.wgrammar import (
    LEGAL_ROLES,
    PATTERN_DISPATCH,
    ROLE_COMPARATOR,
    ROLE_EFFECT_SIGIL,
    ROLE_KEYWORD,
    ROLE_LOGIC,
    ROLE_MEMBERSHIP,
    ROLE_OPERATOR,
    ROLE_PUNCTUATION,
    ROLE_SPECIAL,
    ROLE_STRUCTURAL,
    ROLE_TIER_DIGIT,
    ROLE_TYPE_SIGIL,
    ROLE_UNICODE_DECORATIVE,
    TokenRole,
)


# --- Pattern compilation (one-time at import) ----------------------------

_COMPILED_PATTERNS: Final[tuple[tuple[TokenRole, re.Pattern[str]], ...]] = tuple(
    (role, re.compile(pattern)) for role, pattern in PATTERN_DISPATCH
)


# Direct-membership lookup — checked first because it is O(1) and exact.
_DIRECT_ROLE_LOOKUP: Final[dict[str, TokenRole]] = {
    **{tok: TokenRole.SPECIAL for tok in ROLE_SPECIAL},
    **{tok: TokenRole.TIER_DIGIT for tok in ROLE_TIER_DIGIT},
    **{tok: TokenRole.EFFECT_SIGIL for tok in ROLE_EFFECT_SIGIL},
    **{tok: TokenRole.TYPE_SIGIL for tok in ROLE_TYPE_SIGIL},
    **{tok: TokenRole.KEYWORD for tok in ROLE_KEYWORD},
    **{tok: TokenRole.STRUCTURAL for tok in ROLE_STRUCTURAL},
    **{tok: TokenRole.OPERATOR for tok in ROLE_OPERATOR},
    **{tok: TokenRole.COMPARATOR for tok in ROLE_COMPARATOR},
    **{tok: TokenRole.LOGIC for tok in ROLE_LOGIC},
    **{tok: TokenRole.MEMBERSHIP for tok in ROLE_MEMBERSHIP},
    # v3.0 — punctuation + unicode decoration as legal roles.
    **{tok: TokenRole.PUNCTUATION for tok in ROLE_PUNCTUATION},
    **{tok: TokenRole.UNICODE_DECORATIVE for tok in ROLE_UNICODE_DECORATIVE},
}


# --- Public API ----------------------------------------------------------


def classify_token(token: str) -> TokenRole:
    """Classify a single BPE-emitted token into a structural role.

    Resolution order:
      1. direct membership in a tier-fixed role set (O(1) dict lookup)
      2. anchored regex pattern dispatch in priority order
      3. fallback to ``TokenRole.UNKNOWN`` (the overfit signal)

    Empty strings and ``None`` map to ``UNKNOWN``.
    """
    if not token:
        return TokenRole.UNKNOWN
    role = _DIRECT_ROLE_LOOKUP.get(token)
    if role is not None:
        return role
    for candidate_role, pattern in _COMPILED_PATTERNS:
        if pattern.match(token):
            return candidate_role
    return TokenRole.UNKNOWN


def is_legal_merge(token: str) -> bool:
    """Return True iff the merged token's role is in the W-grammar legal set.

    A merge is W-grammar-legal iff its emitted form classifies into a known
    structural role (a non-``UNKNOWN`` role from
    [a0/wgrammar.LEGAL_ROLES](../a0_qk_constants/wgrammar.py)). Otherwise
    the merge is corpus-overfit: the BPE saw the bigram in training but it
    does not respect any .atm surface-grammar role.
    """
    return classify_token(token) in LEGAL_ROLES


def audit_vocab(vocab: Mapping[str, int]) -> dict[str, Any]:
    """Walk a BPE vocabulary and produce a W-grammar audit report.

    Args:
      vocab: mapping of token-string → token-id (the format returned by
        ``HuggingFace tokenizers Tokenizer.get_vocab()``).

    Returns a JSON-serialisable dict with:
      - ``schema_version``: report schema id
      - ``vocab_size``: total entries in the vocabulary
      - ``role_counts``: count of tokens per role (role-name → int)
      - ``legal_count`` / ``overfit_count``: structural vs overfit totals
      - ``overfit_fraction``: ``overfit_count / vocab_size``
      - ``overfit_examples``: up to 50 example overfit tokens (sorted by id)

    The report is the v2.8 headline metric. Lower overfit_fraction →
    better expected density generalisation.
    """
    role_counts: dict[str, int] = {role.name: 0 for role in TokenRole}
    overfit_examples: list[tuple[int, str]] = []

    for token, tid in vocab.items():
        role = classify_token(token)
        role_counts[role.name] += 1
        if role == TokenRole.UNKNOWN:
            overfit_examples.append((tid, token))

    total = len(vocab)
    legal = total - role_counts[TokenRole.UNKNOWN.name]
    overfit = role_counts[TokenRole.UNKNOWN.name]

    overfit_examples.sort(key=lambda pair: pair[0])
    sample_examples = [tok for _tid, tok in overfit_examples[:50]]

    return {
        "schema_version": "atomadic-lang.wgrammar/v0",
        "vocab_size": total,
        "role_counts": role_counts,
        "legal_count": legal,
        "overfit_count": overfit,
        "overfit_fraction": (overfit / total) if total > 0 else 0.0,
        "overfit_examples": sample_examples,
    }


def merges_by_role(vocab: Mapping[str, int]) -> dict[str, list[str]]:
    """Return tokens grouped by role — useful for inspecting what BPE learned.

    Each role-name maps to a sorted list of tokens with that role. Useful
    in tests and CLI output to confirm e.g. that all tier+effect bigrams
    were learned (or pre-seeded as forced single tokens).
    """
    grouped: dict[str, list[str]] = {role.name: [] for role in TokenRole}
    for token in vocab.keys():
        role = classify_token(token)
        grouped[role.name].append(token)
    for k in grouped:
        grouped[k].sort()
    return grouped
