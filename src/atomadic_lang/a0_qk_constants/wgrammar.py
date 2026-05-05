"""Tier a0 — W-grammar (Van Wijngaarden two-level grammar) constants for BPE merge auditing.

This module encodes the **structural-role lattice** for `.atm` BPE tokens. It is
the data backbone of breakthrough B-016: a custom-trained BPE will, by
construction, learn high-frequency *corpus* merges. Some of those merges are
also high-*structural*-frequency (e.g. ``1π``, ``⟩→i``) — those generalise.
Others are corpus-specific (e.g. ``add⟨``, ``b:i⟩``) — those overfit.

The W-grammar partitions every BPE-emitted token into a structural role.
A merge is **W-grammar-legal** iff its merged content has a known role
(per [a1/wgrammar_audit.py](../a1_at_functions/wgrammar_audit.py)). Merges
without a known role are flagged as overfit signals.

This addresses the v2.7 hold-out density finding: corpus-frequency merges
overfit a training corpus, but role-pair merges generalise across corpora.

Lookup tables only. Zero logic.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Final


# --- Token role lattice --------------------------------------------------


class TokenRole(IntEnum):
    """Structural role assigned to every BPE-emitted token.

    The numeric ordering is descriptive, not lattice-meaningful: roles are
    flat sets, not a total order. The IntEnum form is just to make role
    counts in audit reports stable across runs.
    """

    SPECIAL = 0          # [PAD], [UNK], [BOS], [EOS], [MASK], structural braces
    TIER_DIGIT = 1       # 0, 1, 2, 3, 4
    EFFECT_SIGIL = 2     # π, σ, ω, ι, λ
    TIER_EFFECT = 3      # 1π, 4λ, ... (declaration head bigram)
    TYPE_SIGIL = 4       # i, f, s, b, _, ∅
    COLON_TYPE = 5       # :i, :f, ... (parameter type tag)
    ARROW_TYPE = 6       # →i, →f, ... (return type tag)
    CLOSE_ARROW_TYPE = 7  # ⟩→, ⟩→i, ⟩→[_], ... (param-list close + return)
    COMPOSITE_TYPE = 8   # [_], [s], [i], :[s], :[_], →[_]
    KEYWORD = 9          # pre, post, body, enum
    PACKAGE_HEAD = 10    # @, @calc, @forge, ... (module declarator)
    STRUCTURAL = 11      # ⟨, ⟩, →, ▷, =, :, ,, |, ?, ↦, ⟦, ⟧, s"
    OPERATOR = 12        # +, -, *, /, ** chains
    COMPARATOR = 13      # ≠, ≤, ≥, ≟, <, >
    LOGIC = 14           # ∧, ∨, ¬
    MEMBERSHIP = 15      # ∈, ∉
    IDENT_FRAG = 16      # add, calc, ulate, _x, foo_bar, ... (identifier or its subword)
    OP_CHAIN = 17        # pure-operator merges across operator chars
    LITERAL_INT = 18     # 0, 1, 23, 100, ... (digit-only after first char)
    LITERAL_STR = 19     # "...", s"...", string-content fragments
    # v3.0 — additional roles introduced after V3_EMPIRICAL_FINDING showed
    # that the classifier was too strict for real-Python source.
    PUNCTUATION = 20     # #, ', \, ^, ~, &, `, $ (Python comment/string-escape chars)
    STRUCTURAL_BIGRAM = 21  # self., s:, (s, ⟨s, )), ((, ("‚ [", ,_, s=, s.
    EXPR_BIGRAM = 22     # +b, *b, a+b, -b, /b, b≠, b≠0 (operator-operand merges)
    UNICODE_DECORATIVE = 23  # ·, —, …, ⇒, ∩, box-drawing ─├┤╔╗╚, ▶, ✓, ✗
    # v3.0 Path A.2 — deeper structural prefixes, call-site openers, escapes.
    ESCAPE_SEQUENCE = 24    # \n, \", \\, \n\n, \", \t (Python string escapes)
    CALL_OPEN = 25          # foo(, foo(", obj.method(, Path(, json.dump(, args.get("
    DOTTED_ACCESS = 26      # self.x, obj.attr, .member, json.dump
    ATM_PARAM_TAG = 27      # ⟨ident, ⟨ident:, ⟨ident:s, name:s, _count:i, s:i
    COMPOSITE_TYPE_TAG = 28 # s:[s], s:[_], :s⟩, :s⟩→, :s⟩→s, :_⟩→, (s,_), s:(s,_)
    STRING_JUNCTION = 29    # (", [", {", ,", =", :", ),
    UNKNOWN = 30            # token shape not classified — overfit signal


# --- Role membership tables ----------------------------------------------

# Tokens that must be assigned to fixed roles regardless of pattern matching.
# These are the .atm structural primitives (subset of FORCED_SINGLE_TOKENS).

ROLE_TIER_DIGIT: Final[frozenset[str]] = frozenset({"0", "1", "2", "3", "4"})

ROLE_EFFECT_SIGIL: Final[frozenset[str]] = frozenset({"π", "σ", "ω", "ι", "λ"})

ROLE_TYPE_SIGIL: Final[frozenset[str]] = frozenset({"i", "f", "s", "b", "_", "∅"})

ROLE_KEYWORD: Final[frozenset[str]] = frozenset({
    "pre", "post", "body", "enum",
    # v2.9 — bool literals reserved per atm_grammar.RESERVED
    "true", "false",
})

ROLE_STRUCTURAL: Final[frozenset[str]] = frozenset({
    "⟨", "⟩", "→", "▷", "=", ":", ",", "|", "?", "↦",
    "⟦", "⟧", 's"',
    # v2.9 — additional structural tokens explicit in .atm v0.9 surface grammar
    "!",        # raise sigil (per atm_grammar.RAISE)
    ";",        # clause separator: pre <expr> ; body <expr>
    ".",        # dotted attribute access in qualified names
    "(", ")",   # call / grouping
    "[", "]",   # list / composite-type / comprehension brackets
    "{", "}",   # enum-set brackets
})

# Operator chars include compound forms that the .atm operator translation
# table emits (see atm_grammar.PY_BINOP_TO_ATM).
ROLE_OPERATOR: Final[frozenset[str]] = frozenset({
    "+", "-", "*", "/",
    "**",       # power (per PY_BINOP_TO_ATM)
    "//",       # floor div (per PY_BINOP_TO_ATM)
    "%",        # modulo (per PY_BINOP_TO_ATM)
})

ROLE_COMPARATOR: Final[frozenset[str]] = frozenset({
    "≠", "≤", "≥", "≟", "<", ">",
})

ROLE_LOGIC: Final[frozenset[str]] = frozenset({"∧", "∨", "¬"})

ROLE_MEMBERSHIP: Final[frozenset[str]] = frozenset({"∈", "∉"})

ROLE_SPECIAL: Final[frozenset[str]] = frozenset({
    "[PAD]", "[UNK]", "[BOS]", "[EOS]", "[MASK]",
    "[STRUCTURAL_OPEN]", "[STRUCTURAL_CLOSE]",
    "⟪", "⟫",  # raw structural braces (in case BPE emits them directly)
})


# v3.0 — Punctuation that appears in real Python source (comments, escapes,
# string operators) but is not part of the .atm structural primitive set.
# Universally legitimate; classified as legal because it is corpus-invariant.
# Note: ``@`` and ``!`` are already covered by PACKAGE_HEAD / STRUCTURAL roles
# respectively; do not duplicate them here or direct lookup will shadow the
# more-specific role.
ROLE_PUNCTUATION: Final[frozenset[str]] = frozenset({
    "#", "'", "\\", "^", "~", "&", "`", "$",
})


# v3.0 — Unicode decoration in comments / docstrings of real source. These
# are universally legitimate cosmetic chars; classified as legal because they
# never carry overfit signal (a token with `·` in it is decorative, not
# corpus-specific in any structural sense).
ROLE_UNICODE_DECORATIVE: Final[frozenset[str]] = frozenset({
    "·", "—", "…", "⇒", "∩", "▶", "✓", "✗", "✘", "★", "⭐", "❌", "❎",
    "─", "├", "┤", "╔", "╗", "╚", "╝", "║", "═", "│", "┬", "┴", "┼",
    "▲", "►", "◆", "●", "○", "□", "■",
})


# --- Compound-form patterns ---------------------------------------------
#
# Patterns used by a1/wgrammar_audit.py to recognise multi-character tokens
# that are W-grammar-legal compound roles. Stored here as regex strings to
# keep a0 side-effect-free; a1 compiles them once at module load.
#
# Each pattern matches the ENTIRE token (anchored).
# The order is the role-resolution priority: first match wins.


PATTERN_TIER_EFFECT: Final[str] = r"^[0-4][πσωιλ]$"
PATTERN_COLON_TYPE: Final[str] = r"^:[ifsb_∅]$"
PATTERN_ARROW_TYPE: Final[str] = r"^→[ifsb_∅]$"
PATTERN_CLOSE_ARROW: Final[str] = r"^⟩→$"
PATTERN_CLOSE_ARROW_TYPE: Final[str] = r"^⟩→[ifsb_∅]?$"
# composite types — list-of-T or :[T] / →[T]
PATTERN_COMPOSITE_TYPE: Final[str] = r"^[:→]?\[[ifsb_∅]\]?$"
# package head — @ optionally followed by an identifier
PATTERN_PACKAGE_HEAD: Final[str] = r"^@[A-Za-z_][A-Za-z0-9_]*$|^@$"
# pure identifier or identifier-fragment (letters/digits/underscore only)
PATTERN_IDENT_FRAG: Final[str] = r"^[A-Za-z_][A-Za-z0-9_]*$"
# pure-digit literal
PATTERN_LITERAL_INT: Final[str] = r"^-?[0-9]+$"
# string-literal fragment — opens with " or s" or content between quotes
PATTERN_LITERAL_STR: Final[str] = r'^s?"[^"]*"?$'
# operator chains — only operator characters (incl. compound forms **, //, %)
PATTERN_OPERATOR_CHAIN: Final[str] = r"^[+\-*/%]+$"
# comparator chains — only comparator characters (also allows == >= etc.)
PATTERN_COMPARATOR_CHAIN: Final[str] = r"^[≠≤≥≟<>=]+$"


# v3.0 — STRUCTURAL_BIGRAM: cross-role merges that compose two structural
# primitives without identifier content. e.g. ``self.``, ``s:``, ``(s``,
# ``⟨s``, ``))``, ``((``, ``("``, ``["``, ``,_``, ``s=``, ``s.``,
# ``):``, ``):_``, ``,s``, ``,i``. The pattern recognises:
#   1. paren/bracket/brace pair-character runs:                ()[]{}
#   2. structural sigil + type-sigil composite:                ⟨s, ⟨i, (s, [i, etc.
#   3. type-sigil + structural pair:                           s:, s=, s., s,, s)
#   4. dotted attribute access:                                self., obj.
#   5. comma + leading type sigil:                             ,_, ,i, ,s
PATTERN_STRUCTURAL_BIGRAM: Final[str] = (
    r"^(?:"
    r"[()\[\]{}]{1,4}"                              # paren/bracket runs
    r"|[\(\[\{⟨][ifsb_∅]"                            # opener + type sigil
    r"|[ifsb_∅][:=.,)\]\}]"                          # type sigil + structural
    r"|[A-Za-z_][A-Za-z0-9_]*\.{1,2}"                # ident + dot(s) — self., obj..
    r"|,[_ifsb∅]"                                    # comma + type sigil
    r"|\)[:=.,]"                                     # close paren + structural
    r"|:_[⟩]?[→]?[ifsb_∅]?"                          # :_, :_⟩, :_⟩→, :_⟩→i
    r"|⟨[A-Za-z_]"                                   # open angle + ident start
    r"|[ifsb_∅]\)"                                   # type sigil + close paren
    r")$"
)


# v3.0 — EXPR_BIGRAM: operator-operand merges. e.g. ``+b``, ``*b``, ``a+b``,
# ``-b``, ``/b``, ``b≠``, ``b≠0``, ``a-b``, ``a*b``, ``a/b``. These are the
# most universally-legitimate merges in real expression-heavy code; the BPE
# learns them quickly because operators-with-vars are everywhere.
PATTERN_EXPR_BIGRAM: Final[str] = (
    r"^(?:"
    r"[+\-*/%][A-Za-z_0-9]+"                         # +b, -x, *self
    r"|[A-Za-z_0-9]+[+\-*/%][A-Za-z_0-9]+"           # a+b, x*y, self+1
    r"|[A-Za-z_0-9]+[≠≤≥≟<>=][0-9A-Za-z_]*"          # b≠0, x<10, n≥0
    r")$"
)


# --- v3.0 Path A.2 — additional patterns for the long tail of legitimate
# tokens that survived Path A as UNKNOWN.

# ESCAPE_SEQUENCE: Python string escape fragments. \n, \t, \", \\, plus
# repeated forms (\n\n) and shape \"\".
PATTERN_ESCAPE_SEQUENCE: Final[str] = (
    r"^(?:"
    r"\\[nrtbfvae0]+"                                 # \n, \t, \r, \nn..
    r"|\\[\"']+\\?[\"']*"                             # \", \', \"\"
    r"|\\\\+"                                          # \\, \\\\
    r"|(?:\\n)+|(?:\\t)+|(?:\\\")+|(?:\\')+"          # repeated escape units
    r"|,\\n+|\\n+,"                                    # ,\n  \n,
    r")$"
)

# CALL_OPEN: identifier followed by ``(`` (optionally with one quote). Covers
# ``foo(``, ``foo(\"``, ``obj.method(``, ``json.dump(``, ``args.get(\"``.
PATTERN_CALL_OPEN: Final[str] = (
    r"^(?:"
    r"[A-Za-z_][A-Za-z0-9_]*\([\"']?"                 # foo(, foo("
    r"|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\([\"']?"  # obj.method(
    r"|[A-Za-z_][A-Za-z0-9_]*\[[\"']"                 # foo[", bar['
    r")$"
)

# DOTTED_ACCESS: dotted attribute access without a call. ``self.x``,
# ``obj.attr``, ``.member``, ``json.dump`` (the bare reference).
PATTERN_DOTTED_ACCESS: Final[str] = (
    r"^(?:"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"  # obj.attr, self.x.y
    r"|\.[A-Za-z_][A-Za-z0-9_]*"                              # .member
    r")$"
)

# ATM_PARAM_TAG: declaration-shaped identifier-with-type-tag. ``name:s``,
# ``_count:i``, ``⟨ident``, ``⟨ident:``, ``⟨ident:s``, ``s:i``, ``s:f``.
PATTERN_ATM_PARAM_TAG: Final[str] = (
    r"^(?:"
    r"⟨[A-Za-z_][A-Za-z0-9_]*"                        # ⟨ident
    r"(?::[ifsb_∅])?(?:\[[ifsb_∅]\]?)?$"               #   :type optional, [type] optional (re-anchored)
    r"|^⟨[A-Za-z_][A-Za-z0-9_]*:?$"                    # ⟨ident or ⟨ident:
    r"|^[A-Za-z_][A-Za-z0-9_]*:[ifsb_∅]$"              # name:s, _count:i
    r"|^[ifsb_∅]:[ifsb_∅]$"                            # s:i, _:s
    r")"
)

# COMPOSITE_TYPE_TAG: composite type continuations specific to .atm.
# ``s:[s]``, ``s:[_]``, ``:s⟩``, ``:s⟩→``, ``:s⟩→s``, ``:_⟩→``, ``(s,_)``,
# ``s:(s,_)``, ``,_)``, ``{s:_``, ``{s:_}``, ``⟨⟩→``, ``⟨⟩→i``.
PATTERN_COMPOSITE_TYPE_TAG: Final[str] = (
    r"^(?:"
    r"[ifsb_∅]:\[[ifsb_∅]?\]?"                         # s:[s], s:[_], _:[s
    r"|:[ifsb_∅]?⟩→?[ifsb_∅]?"                          # :s⟩, :s⟩→, :s⟩→s, :_⟩→, :_⟩→i
    r"|\([ifsb_∅](?:,[ifsb_∅])*\)?"                     # (s,_), (s,_), (_
    r"|[ifsb_∅]:\([ifsb_∅](?:,[ifsb_∅])*\)?"            # s:(s,_), s:(s,
    r"|\{[ifsb_∅]:[ifsb_∅]?\}?"                         # {s:_, {s:_}, {s:
    r"|,[ifsb_∅]\)"                                     # ,_)
    r"|⟨⟩→[ifsb_∅]?"                                   # ⟨⟩→, ⟨⟩→i
    r")$"
)

# STRING_JUNCTION: structural boundary + string-quote. Captures merges where
# BPE bridges a structural primitive into a string literal opener: ``("``,
# ``["``, ``{"``, ``,"``, ``="``, ``:"``, ``")``, ``"]``.
PATTERN_STRING_JUNCTION: Final[str] = (
    r"^(?:"
    r"[(\[\{,=:][\"'`]{1,2}"                          # opener + quote: ("  [" {" ," =" :"
    r"|[\"'`]{1,2}[,)\]\}=:]"                          # quote + closer: ", ') ", "} =" :"
    r"|[\"'`]{2,}"                                     # multi-quote: """, ''', ``
    r"|=[(\[][\"']?"                                   # =( =[ =(" =["
    r"|/[\"']"                                         # /"  /'
    r")$"
)


# --- Resolution-order list ----------------------------------------------
#
# Used by a1/wgrammar_audit.classify_token to dispatch in priority order.
# Tuple of (TokenRole, pattern_string). a1 compiles each pattern lazily.


PATTERN_DISPATCH: Final[tuple[tuple[TokenRole, str], ...]] = (
    (TokenRole.TIER_EFFECT, PATTERN_TIER_EFFECT),
    (TokenRole.CLOSE_ARROW_TYPE, PATTERN_CLOSE_ARROW),       # ⟩→
    (TokenRole.CLOSE_ARROW_TYPE, PATTERN_CLOSE_ARROW_TYPE),  # ⟩→i
    (TokenRole.COLON_TYPE, PATTERN_COLON_TYPE),
    (TokenRole.ARROW_TYPE, PATTERN_ARROW_TYPE),
    (TokenRole.COMPOSITE_TYPE, PATTERN_COMPOSITE_TYPE),
    (TokenRole.PACKAGE_HEAD, PATTERN_PACKAGE_HEAD),
    (TokenRole.LITERAL_INT, PATTERN_LITERAL_INT),
    (TokenRole.LITERAL_STR, PATTERN_LITERAL_STR),
    # v3.0 Path A.2 — high-priority specific shapes BEFORE generic structural
    # bigrams + ident frag. Order: most-specific first.
    (TokenRole.ESCAPE_SEQUENCE, PATTERN_ESCAPE_SEQUENCE),
    (TokenRole.COMPOSITE_TYPE_TAG, PATTERN_COMPOSITE_TYPE_TAG),
    (TokenRole.ATM_PARAM_TAG, PATTERN_ATM_PARAM_TAG),
    (TokenRole.CALL_OPEN, PATTERN_CALL_OPEN),
    (TokenRole.DOTTED_ACCESS, PATTERN_DOTTED_ACCESS),
    (TokenRole.STRING_JUNCTION, PATTERN_STRING_JUNCTION),
    # v3.0 Path A — try structural bigrams BEFORE pure ident, otherwise ``self.``
    # would classify as IDENT_FRAG and miss its compound nature.
    (TokenRole.STRUCTURAL_BIGRAM, PATTERN_STRUCTURAL_BIGRAM),
    # v3.0 Path A — expression bigrams must come before IDENT_FRAG so that
    # ``a+b`` doesn't fall through (IDENT_FRAG is ident-only anyway, but
    # ordering keeps EXPR_BIGRAM precedence explicit).
    (TokenRole.EXPR_BIGRAM, PATTERN_EXPR_BIGRAM),
    (TokenRole.IDENT_FRAG, PATTERN_IDENT_FRAG),
    (TokenRole.OP_CHAIN, PATTERN_OPERATOR_CHAIN),
    (TokenRole.OP_CHAIN, PATTERN_COMPARATOR_CHAIN),
)


# --- Roles considered W-grammar-legal -----------------------------------
#
# A merge whose final token classifies into one of these roles is structural
# (generalises across corpora). UNKNOWN = corpus-overfit signal.


LEGAL_ROLES: Final[frozenset[TokenRole]] = frozenset({
    TokenRole.SPECIAL,
    TokenRole.TIER_DIGIT,
    TokenRole.EFFECT_SIGIL,
    TokenRole.TIER_EFFECT,
    TokenRole.TYPE_SIGIL,
    TokenRole.COLON_TYPE,
    TokenRole.ARROW_TYPE,
    TokenRole.CLOSE_ARROW_TYPE,
    TokenRole.COMPOSITE_TYPE,
    TokenRole.KEYWORD,
    TokenRole.PACKAGE_HEAD,
    TokenRole.STRUCTURAL,
    TokenRole.OPERATOR,
    TokenRole.COMPARATOR,
    TokenRole.LOGIC,
    TokenRole.MEMBERSHIP,
    TokenRole.IDENT_FRAG,
    TokenRole.OP_CHAIN,
    TokenRole.LITERAL_INT,
    TokenRole.LITERAL_STR,
    # v3.0 — additional legal roles after V3_EMPIRICAL_FINDING.
    TokenRole.PUNCTUATION,
    TokenRole.STRUCTURAL_BIGRAM,
    TokenRole.EXPR_BIGRAM,
    TokenRole.UNICODE_DECORATIVE,
    # v3.0 Path A.2 — extended legal roles for the long tail.
    TokenRole.ESCAPE_SEQUENCE,
    TokenRole.CALL_OPEN,
    TokenRole.DOTTED_ACCESS,
    TokenRole.ATM_PARAM_TAG,
    TokenRole.COMPOSITE_TYPE_TAG,
    TokenRole.STRING_JUNCTION,
})
