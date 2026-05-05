"""Tests for v2.8 W-grammar BPE merge auditor (B-016).

Coverage:
  - a0 role tables are well-formed (no overlaps that would cause
    ambiguous classification)
  - a1 ``classify_token`` resolves each forced single token to the
    expected role
  - a1 ``is_legal_merge`` rejects clearly-overfit shapes
  - a1 ``audit_vocab`` produces a well-shaped report on a synthetic vocab
  - a3 ``audit_tokenizer_file`` round-trips through saved-tokenizer JSON
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atomadic_lang.a0_qk_constants.wgrammar import (
    LEGAL_ROLES,
    ROLE_EFFECT_SIGIL,
    ROLE_KEYWORD,
    ROLE_TIER_DIGIT,
    ROLE_TYPE_SIGIL,
    TokenRole,
)
from atomadic_lang.a1_at_functions.wgrammar_audit import (
    audit_vocab,
    classify_token,
    is_legal_merge,
    merges_by_role,
)


TOKENIZER_V15 = Path(__file__).resolve().parent.parent / "tokenizer_v15.json"


# --- a0 sanity -----------------------------------------------------------


def test_role_tables_disjoint() -> None:
    """Forced single-token role sets do not collide on the same string."""
    sets = {
        "tier_digit": ROLE_TIER_DIGIT,
        "effect_sigil": ROLE_EFFECT_SIGIL,
        "type_sigil": ROLE_TYPE_SIGIL,
        "keyword": ROLE_KEYWORD,
    }
    for name_a, set_a in sets.items():
        for name_b, set_b in sets.items():
            if name_a >= name_b:
                continue
            collision = set_a & set_b
            assert not collision, (
                f"role overlap between {name_a} and {name_b}: {collision}"
            )


def test_legal_roles_excludes_unknown() -> None:
    assert TokenRole.UNKNOWN not in LEGAL_ROLES


# --- a1 classify_token --------------------------------------------------


@pytest.mark.parametrize("token,expected", [
    # Tier digits
    ("0", TokenRole.TIER_DIGIT),
    ("4", TokenRole.TIER_DIGIT),
    # Effect sigils
    ("π", TokenRole.EFFECT_SIGIL),
    ("λ", TokenRole.EFFECT_SIGIL),
    # Tier+effect bigrams (compound)
    ("1π", TokenRole.TIER_EFFECT),
    ("4ι", TokenRole.TIER_EFFECT),
    # Type sigils
    ("i", TokenRole.TYPE_SIGIL),
    ("∅", TokenRole.TYPE_SIGIL),
    # Colon-type and arrow-type
    (":i", TokenRole.COLON_TYPE),
    ("→s", TokenRole.ARROW_TYPE),
    # Close-arrow combos
    ("⟩→", TokenRole.CLOSE_ARROW_TYPE),
    ("⟩→i", TokenRole.CLOSE_ARROW_TYPE),
    # Composite types
    ("[_]", TokenRole.COMPOSITE_TYPE),
    (":[s", TokenRole.COMPOSITE_TYPE),
    ("→[i]", TokenRole.COMPOSITE_TYPE),
    # Keywords
    ("pre", TokenRole.KEYWORD),
    ("enum", TokenRole.KEYWORD),
    # Package head
    ("@calc", TokenRole.PACKAGE_HEAD),
    ("@", TokenRole.PACKAGE_HEAD),
    # Structural punctuation
    ("⟨", TokenRole.STRUCTURAL),
    ("→", TokenRole.STRUCTURAL),
    ("=", TokenRole.STRUCTURAL),
    # Operators / comparators / logic / membership
    ("+", TokenRole.OPERATOR),
    ("≠", TokenRole.COMPARATOR),
    ("∧", TokenRole.LOGIC),
    ("∈", TokenRole.MEMBERSHIP),
    # Identifier fragments
    ("add", TokenRole.IDENT_FRAG),
    ("calc", TokenRole.IDENT_FRAG),
    ("ulate", TokenRole.IDENT_FRAG),
    ("foo_bar", TokenRole.IDENT_FRAG),
    # Literal int
    ("42", TokenRole.LITERAL_INT),
    # Special tokens
    ("[PAD]", TokenRole.SPECIAL),
    ("[UNK]", TokenRole.SPECIAL),
    # v2.9 — additional structural tokens
    ("!", TokenRole.STRUCTURAL),
    (";", TokenRole.STRUCTURAL),
    (".", TokenRole.STRUCTURAL),
    ("(", TokenRole.STRUCTURAL),
    (")", TokenRole.STRUCTURAL),
    ("[", TokenRole.STRUCTURAL),
    ("]", TokenRole.STRUCTURAL),
    ("{", TokenRole.STRUCTURAL),
    ("}", TokenRole.STRUCTURAL),
    # v2.9 — compound operators
    ("**", TokenRole.OPERATOR),
    ("//", TokenRole.OPERATOR),
    ("%", TokenRole.OPERATOR),
    # v2.9 — bool keyword literals
    ("true", TokenRole.KEYWORD),
    ("false", TokenRole.KEYWORD),
])
def test_classify_token_known_roles(token: str, expected: TokenRole) -> None:
    assert classify_token(token) == expected


@pytest.mark.parametrize("token", [
    # Role-mixing (BPE corpus-overfit signals)
    "add⟨",   # identifier + structural
    "=a+",    # structural + identifier + operator
    "⟩=",     # structural + structural without grammar role
    "1π add", # contains whitespace — not a single BPE token shape
    "",       # empty string
    # v3.0 NOTE: tokens previously listed as overfit but reclassified after
    # the V3_EMPIRICAL_FINDING:
    #   - "a:i" now matches STRUCTURAL_BIGRAM (type-sigil + structural)
    #   - "x≠0" now matches EXPR_BIGRAM (ident + comparator + literal —
    #     a universal expression pattern, not corpus-specific overfit)
])
def test_classify_token_unknown_roles_for_overfit_shapes(token: str) -> None:
    assert classify_token(token) == TokenRole.UNKNOWN


# --- a1 is_legal_merge --------------------------------------------------


def test_is_legal_merge_true_for_structural_tokens() -> None:
    for tok in ["1π", ":i", "⟩→i", "add", "[_]", "enum", "@calc"]:
        assert is_legal_merge(tok), f"expected legal: {tok!r}"


def test_is_legal_merge_false_for_overfit_shapes() -> None:
    # v3.0: "x≠0" reclassified as EXPR_BIGRAM (universal expression pattern),
    # so it is now legal. The remaining shapes still mix roles in ways the
    # classifier does not recognise as structural.
    for tok in ["add⟨", "=a+", "⟩=add"]:
        assert not is_legal_merge(tok), f"expected overfit: {tok!r}"


# --- v3.0 — new role coverage --------------------------------------------


@pytest.mark.parametrize("token,expected", [
    # PUNCTUATION
    ("#", TokenRole.PUNCTUATION),
    ("'", TokenRole.PUNCTUATION),
    ("\\", TokenRole.PUNCTUATION),
    ("^", TokenRole.PUNCTUATION),
    ("~", TokenRole.PUNCTUATION),
    # STRUCTURAL_BIGRAM (the shapes that don't match a more-specific A.2 role)
    ("self.", TokenRole.STRUCTURAL_BIGRAM),
    ("s:", TokenRole.STRUCTURAL_BIGRAM),
    ("))", TokenRole.STRUCTURAL_BIGRAM),
    ("((", TokenRole.STRUCTURAL_BIGRAM),
    (",_", TokenRole.STRUCTURAL_BIGRAM),
    # EXPR_BIGRAM
    ("a+b", TokenRole.EXPR_BIGRAM),
    ("a-b", TokenRole.EXPR_BIGRAM),
    ("x*y", TokenRole.EXPR_BIGRAM),
    ("x≠0", TokenRole.EXPR_BIGRAM),
    ("n≥0", TokenRole.EXPR_BIGRAM),
    # UNICODE_DECORATIVE
    ("·", TokenRole.UNICODE_DECORATIVE),
    ("—", TokenRole.UNICODE_DECORATIVE),
    ("…", TokenRole.UNICODE_DECORATIVE),
    ("✓", TokenRole.UNICODE_DECORATIVE),
    ("✗", TokenRole.UNICODE_DECORATIVE),
    ("─", TokenRole.UNICODE_DECORATIVE),
])
def test_classify_token_v3_new_roles(token: str, expected: TokenRole) -> None:
    """v3.0 expanded role coverage from V3_EMPIRICAL_FINDING.md."""
    assert classify_token(token) == expected


@pytest.mark.parametrize("token,expected", [
    # ESCAPE_SEQUENCE
    ("\\n", TokenRole.ESCAPE_SEQUENCE),
    ("\\t", TokenRole.ESCAPE_SEQUENCE),
    ("\\\"", TokenRole.ESCAPE_SEQUENCE),
    ("\\n\\n", TokenRole.ESCAPE_SEQUENCE),
    # CALL_OPEN
    ("foo(", TokenRole.CALL_OPEN),
    ("Path(", TokenRole.CALL_OPEN),
    ("foo(\"", TokenRole.CALL_OPEN),
    ("get(\"", TokenRole.CALL_OPEN),
    ("obj.method(", TokenRole.CALL_OPEN),
    ("json.dump(", TokenRole.CALL_OPEN),
    ("args.get(\"", TokenRole.CALL_OPEN),
    ("foo[\"", TokenRole.CALL_OPEN),
    # DOTTED_ACCESS
    ("self.x", TokenRole.DOTTED_ACCESS),
    ("obj.attr", TokenRole.DOTTED_ACCESS),
    (".member", TokenRole.DOTTED_ACCESS),
    (".re", TokenRole.DOTTED_ACCESS),
    ("json.dump", TokenRole.DOTTED_ACCESS),
    # ATM_PARAM_TAG
    ("⟨self", TokenRole.ATM_PARAM_TAG),
    ("⟨self:", TokenRole.ATM_PARAM_TAG),
    ("⟨schema", TokenRole.ATM_PARAM_TAG),
    ("name:s", TokenRole.ATM_PARAM_TAG),
    ("_count:i", TokenRole.ATM_PARAM_TAG),
    ("s:i", TokenRole.ATM_PARAM_TAG),
    # COMPOSITE_TYPE_TAG
    ("(s", TokenRole.COMPOSITE_TYPE_TAG),         # paren-tuple opener
    ("⟨s", TokenRole.ATM_PARAM_TAG),               # angle-ident still ATM_PARAM_TAG
    ("s:[s]", TokenRole.COMPOSITE_TYPE_TAG),
    ("s:[_]", TokenRole.COMPOSITE_TYPE_TAG),
    (":s⟩", TokenRole.COMPOSITE_TYPE_TAG),
    (":s⟩→s", TokenRole.COMPOSITE_TYPE_TAG),
    ("(s,_)", TokenRole.COMPOSITE_TYPE_TAG),
    (",_)", TokenRole.COMPOSITE_TYPE_TAG),
    ("⟨⟩→i", TokenRole.COMPOSITE_TYPE_TAG),
    # STRING_JUNCTION
    # ``""`` is a *complete* empty string literal (LITERAL_STR), not a
    # junction; the dispatch correctly classifies it earlier.
    ("(\"", TokenRole.STRING_JUNCTION),
    ("[\"", TokenRole.STRING_JUNCTION),
    (",\"", TokenRole.STRING_JUNCTION),
    ("=\"", TokenRole.STRING_JUNCTION),
])
def test_classify_token_v3_path_a2_roles(token: str, expected: TokenRole) -> None:
    """v3.0 Path A.2: deeper structural prefixes, escapes, call sites."""
    assert classify_token(token) == expected


def test_v3_new_roles_are_legal() -> None:
    """All v3.0 + Path A.2 + Path A.3 roles must be in LEGAL_ROLES."""
    for role in (
        # Path A
        TokenRole.PUNCTUATION,
        TokenRole.STRUCTURAL_BIGRAM,
        TokenRole.EXPR_BIGRAM,
        TokenRole.UNICODE_DECORATIVE,
        # Path A.2
        TokenRole.ESCAPE_SEQUENCE,
        TokenRole.CALL_OPEN,
        TokenRole.DOTTED_ACCESS,
        TokenRole.ATM_PARAM_TAG,
        TokenRole.COMPOSITE_TYPE_TAG,
        TokenRole.STRING_JUNCTION,
        # Path A.3
        TokenRole.ENCODING_NOISE,
        TokenRole.DUNDER,
    ):
        assert role in LEGAL_ROLES, f"v3.0+ role {role.name} missing from LEGAL_ROLES"


@pytest.mark.parametrize("token,expected", [
    # ENCODING_NOISE — single chars (direct lookup)
    ("�", TokenRole.ENCODING_NOISE),                  # replacement
    (" ", TokenRole.ENCODING_NOISE),                  # non-breaking space
    ("​", TokenRole.ENCODING_NOISE),                  # zero-width space
    ("﻿", TokenRole.ENCODING_NOISE),                  # BOM
    # ENCODING_NOISE — multi-char runs (pattern fallback)
    ("� ", TokenRole.ENCODING_NOISE),
    ("​‌‍", TokenRole.ENCODING_NOISE),
    # DUNDER
    ("__", TokenRole.DUNDER),
    ("___", TokenRole.DUNDER),
    ("____", TokenRole.DUNDER),
    ("__init__", TokenRole.DUNDER),
    ("__main__", TokenRole.DUNDER),
    ("__name__", TokenRole.DUNDER),
    ("__class__", TokenRole.DUNDER),
    ("__repr__", TokenRole.DUNDER),
])
def test_classify_token_v3_path_a3_roles(token: str, expected: TokenRole) -> None:
    """v3.2 Path A.3: encoding-noise + dunder coverage."""
    assert classify_token(token) == expected


def test_dunder_takes_priority_over_ident_frag() -> None:
    """Dispatch order must put DUNDER before IDENT_FRAG so __init__ is DUNDER."""
    # __init__ is a valid ident shape but is more-specifically a dunder.
    assert classify_token("__init__") == TokenRole.DUNDER
    # Plain ident with single underscore stays IDENT_FRAG.
    assert classify_token("_init") == TokenRole.IDENT_FRAG
    assert classify_token("init_") == TokenRole.IDENT_FRAG


# --- a1 audit_vocab -----------------------------------------------------


def test_audit_vocab_all_legal() -> None:
    vocab = {"1π": 0, "add": 1, ":i": 2, "⟩→i": 3, "[PAD]": 4}
    report = audit_vocab(vocab)
    assert report["vocab_size"] == 5
    assert report["legal_count"] == 5
    assert report["overfit_count"] == 0
    assert report["overfit_fraction"] == 0.0
    assert report["overfit_examples"] == []


def test_audit_vocab_mixed() -> None:
    vocab = {"1π": 0, "add⟨": 1, "=a+": 2, ":i": 3}
    report = audit_vocab(vocab)
    assert report["vocab_size"] == 4
    assert report["legal_count"] == 2
    assert report["overfit_count"] == 2
    assert report["overfit_fraction"] == 0.5
    assert sorted(report["overfit_examples"]) == sorted(["add⟨", "=a+"])


def test_audit_vocab_role_counts_sum() -> None:
    vocab = {"1π": 0, "add": 1, ":i": 2, "garbage⟨add": 3}
    report = audit_vocab(vocab)
    assert sum(report["role_counts"].values()) == report["vocab_size"]


def test_merges_by_role_groups() -> None:
    vocab = {"1π": 0, "2σ": 1, "add": 2, "calc": 3, ":i": 4}
    grouped = merges_by_role(vocab)
    assert "1π" in grouped[TokenRole.TIER_EFFECT.name]
    assert "2σ" in grouped[TokenRole.TIER_EFFECT.name]
    assert "add" in grouped[TokenRole.IDENT_FRAG.name]
    assert ":i" in grouped[TokenRole.COLON_TYPE.name]
    # The grouped lists are sorted.
    assert grouped[TokenRole.TIER_EFFECT.name] == sorted(
        grouped[TokenRole.TIER_EFFECT.name]
    )


def test_audit_vocab_empty() -> None:
    report = audit_vocab({})
    assert report["vocab_size"] == 0
    assert report["legal_count"] == 0
    assert report["overfit_count"] == 0
    assert report["overfit_fraction"] == 0.0


# --- a3 round-trip through a real saved tokenizer -----------------------


@pytest.mark.skipif(not TOKENIZER_V15.exists(), reason="v1.5 tokenizer not present")
def test_audit_tokenizer_file_v15() -> None:
    """The v1.5 tokenizer should be auditable end-to-end and produce a sane report."""
    from atomadic_lang.a3_og_features.wgrammar_feature import audit_tokenizer_file

    report = audit_tokenizer_file(TOKENIZER_V15)
    assert report["schema_version"] == "atomadic-lang.wgrammar/v0"
    assert report["vocab_size"] > 0
    assert report["legal_count"] + report["overfit_count"] == report["vocab_size"]
    assert 0.0 <= report["overfit_fraction"] <= 1.0
    # Forced single tokens should always classify into known roles, so the
    # legal count must be at least the size of FORCED_SINGLE_TOKENS minus
    # those that aren't in the vocab.
    assert report["legal_count"] >= 30


@pytest.mark.skipif(not TOKENIZER_V15.exists(), reason="v1.5 tokenizer not present")
def test_audit_tokenizer_summary_renders() -> None:
    from atomadic_lang.a3_og_features.wgrammar_feature import (
        audit_tokenizer_file,
        summarise_audit,
    )

    report = audit_tokenizer_file(TOKENIZER_V15)
    summary = summarise_audit(report)
    assert "W-grammar audit" in summary
    assert "vocab_size:" in summary
    assert "overfit_fraction:" in summary
