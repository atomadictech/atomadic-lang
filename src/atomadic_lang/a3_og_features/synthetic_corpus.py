"""Tier a3 — synthetic NL→.atm pair generator for v2.5 corpus growth.

The natural Forge corpus has 138 decls — below every published
fine-tuning floor (3-10k per arXiv:2412.13337). This feature generates
synthetic (natural-language description, .atm declaration) pairs from
templates, growing the BPE training corpus by 10-50× without requiring
human authoring or a frontier-model API call.

The templates are deliberately narrow at v2.5: arithmetic, list ops,
string ops, simple class types. Coverage of `.atm`'s full semantic
surface comes from the natural Forge corpus + future production code.

Imports a0, a1.
"""

from __future__ import annotations

import random
from typing import TypedDict

from ..a0_qk_constants.atm_types import LoweredDecl, LoweredParam


class SyntheticPair(TypedDict):
    """One (NL description, .atm decl) training pair."""

    nl: str           # natural-language description
    atm_line: str     # one-line .atm rendering
    decl: LoweredDecl  # structured form (for downstream tools)


# --- vocabulary banks for templates --------------------------------------

# Variable-name pool — balanced single-letter + short names.
_VAR_NAMES = ["a", "b", "c", "x", "y", "z", "i", "j", "k", "n", "m",
              "lhs", "rhs", "val", "out", "tmp", "acc", "cnt", "idx", "key"]

_LIST_NAMES = ["xs", "ys", "items", "values", "data", "entries", "buf", "rows"]

_STR_NAMES = ["s", "name", "label", "msg", "text", "line", "key", "tag", "id"]

# Function-name patterns for the synthesizer.
_ARITH_FUNCS = {
    "add":   ("+", "Adds {a} and {b}.", "i", "i", "i"),
    "sub":   ("-", "Subtracts {b} from {a}.", "i", "i", "i"),
    "mul":   ("*", "Multiplies {a} and {b}.", "i", "i", "i"),
    "max":   (None, "Returns the greater of {a} and {b}.", "i", "i", "i"),
    "min":   (None, "Returns the lesser of {a} and {b}.", "i", "i", "i"),
    "diff":  (None, "Returns the absolute difference of {a} and {b}.", "i", "i", "i"),
    "pow":   ("**", "Raises {a} to the power {b}.", "i", "i", "i"),
    "scale": ("*", "Multiplies {a} by {b}.", "f", "f", "f"),
}

_LIST_OPS = {
    "head":     ("Returns the first element of {xs}.", "[i]", "i"),
    "tail":     ("Returns all but the first element of {xs}.", "[i]", "[i]"),
    "length":   ("Returns the length of {xs}.", "[i]", "i"),
    "sum":      ("Sums the elements of {xs}.", "[i]", "i"),
    "max_of":   ("Returns the maximum element of {xs}.", "[i]", "i"),
    "min_of":   ("Returns the minimum element of {xs}.", "[i]", "i"),
    "reverse":  ("Returns {xs} in reverse order.", "[i]", "[i]"),
    "is_empty": ("Returns true if {xs} is empty.", "[_]", "b"),
    "double":   ("Returns each element of {xs} doubled.", "[i]", "[i]"),
}

_STR_OPS = {
    "upper":    ("Returns {s} in uppercase.", "s", "s"),
    "lower":    ("Returns {s} in lowercase.", "s", "s"),
    "trim":     ("Returns {s} with whitespace stripped.", "s", "s"),
    "len_of":   ("Returns the length of {s}.", "s", "i"),
    "is_blank": ("Returns true if {s} is empty or whitespace.", "s", "b"),
    "echo":     ("Returns {s} unchanged.", "s", "s"),
}

# Class shapes for synthetic record types.
_RECORD_TEMPLATES = [
    ("Point",     [("x", "i"), ("y", "i")],
        "A 2D integer point with coordinates x and y."),
    ("Range",     [("lo", "i"), ("hi", "i")],
        "An integer range from lo to hi."),
    ("Pair",      [("first", "_"), ("second", "_")],
        "A pair of values."),
    ("Counter",   [("value", "i")],
        "A counter holding an integer value."),
    ("Logger",    [("prefix", "s"), ("count", "i")],
        "A logger with a prefix string and message count."),
    ("ConfigEntry", [("key", "s"), ("value", "s"), ("required", "b")],
        "A single configuration entry."),
    ("ScoreCard", [("name", "s"), ("score", "f"), ("rank", "i")],
        "A score record for a participant."),
]


# --- synthesizers --------------------------------------------------------


def _synth_arith(rng: random.Random, package: str = "synth") -> SyntheticPair:
    """Synthesize an a1 arithmetic function pair."""
    name = rng.choice(list(_ARITH_FUNCS.keys()))
    op, nl_template, t_a, t_b, t_ret = _ARITH_FUNCS[name]
    a_name = rng.choice(_VAR_NAMES)
    b_name = rng.choice([v for v in _VAR_NAMES if v != a_name])
    nl = nl_template.format(a=a_name, b=b_name)

    # Body
    if op is not None:
        body = f"{a_name}{op}{b_name}"
    else:
        # Use a polymorphic-ish call for max/min/diff/etc.
        if name == "max":
            body = f"{a_name}>{b_name}?{a_name}:{b_name}"
        elif name == "min":
            body = f"{a_name}<{b_name}?{a_name}:{b_name}"
        elif name == "diff":
            body = f"{a_name}>{b_name}?{a_name}-{b_name}:{b_name}-{a_name}"
        else:
            body = f"{a_name}+{b_name}"

    atm_line = f"1π {name} ⟨{a_name}:{t_a} {b_name}:{t_b}⟩→{t_ret} = {body}"
    decl = LoweredDecl(
        tier=1, effect="π", name=name,
        params=[
            LoweredParam(name=a_name, type_sigil=t_a),
            LoweredParam(name=b_name, type_sigil=t_b),
        ],
        return_sigil=t_ret,
        body_form="inline", body=body, pre="", post="",
        source_path=f"<synth/{package}>", source_lineno=0,
    )
    return SyntheticPair(nl=nl, atm_line=atm_line, decl=decl)


def _synth_list(rng: random.Random, package: str = "synth") -> SyntheticPair:
    """Synthesize an a1 list-op pair."""
    name = rng.choice(list(_LIST_OPS.keys()))
    nl_template, t_in, t_ret = _LIST_OPS[name]
    xs_name = rng.choice(_LIST_NAMES)
    nl = nl_template.format(xs=xs_name)

    # Generate a plausible body — these are mostly placeholders for
    # the corpus; the BPE learns the structural patterns.
    bodies = {
        "head":     f"{xs_name}[0]",
        "tail":     f"{xs_name}[1:]",
        "length":   f"|{xs_name}|",
        "sum":      f"sum({xs_name})",
        "max_of":   f"max({xs_name})",
        "min_of":   f"min({xs_name})",
        "reverse":  f"{xs_name}[::-1]",
        "is_empty": f"|{xs_name}|≟0",
        "double":   f"[2*x | x∈{xs_name}]",
    }
    body = bodies[name]
    atm_line = f"1π {name} ⟨{xs_name}:{t_in}⟩→{t_ret} = {body}"
    decl = LoweredDecl(
        tier=1, effect="π", name=name,
        params=[LoweredParam(name=xs_name, type_sigil=t_in)],
        return_sigil=t_ret,
        body_form="inline", body=body, pre="", post="",
        source_path=f"<synth/{package}>", source_lineno=0,
    )
    return SyntheticPair(nl=nl, atm_line=atm_line, decl=decl)


def _synth_string(rng: random.Random, package: str = "synth") -> SyntheticPair:
    """Synthesize an a1 string-op pair."""
    name = rng.choice(list(_STR_OPS.keys()))
    nl_template, t_in, t_ret = _STR_OPS[name]
    s_name = rng.choice(_STR_NAMES)
    nl = nl_template.format(s=s_name)

    bodies = {
        "upper":    f"{s_name}.upper()",
        "lower":    f"{s_name}.lower()",
        "trim":     f"{s_name}.strip()",
        "len_of":   f"|{s_name}|",
        "is_blank": f"|{s_name}.strip()|≟0",
        "echo":     f"{s_name}",
    }
    body = bodies[name]
    atm_line = f"1π {name} ⟨{s_name}:{t_in}⟩→{t_ret} = {body}"
    decl = LoweredDecl(
        tier=1, effect="π", name=name,
        params=[LoweredParam(name=s_name, type_sigil=t_in)],
        return_sigil=t_ret,
        body_form="inline", body=body, pre="", post="",
        source_path=f"<synth/{package}>", source_lineno=0,
    )
    return SyntheticPair(nl=nl, atm_line=atm_line, decl=decl)


def _synth_record(rng: random.Random, package: str = "synth") -> SyntheticPair:
    """Synthesize a tier-0 record-type (TypedDict-style) decl."""
    cls_name, fields, nl = rng.choice(_RECORD_TEMPLATES)
    params = [LoweredParam(name=fn, type_sigil=ts) for fn, ts in fields]
    field_str = " ".join(f"{p['name']}:{p['type_sigil']}" for p in params)
    atm_line = f"0 {cls_name} ⟨{field_str}⟩"
    decl = LoweredDecl(
        tier=0, effect="", name=cls_name,
        params=params,
        return_sigil="",
        body_form="class", body="", pre="", post="",
        source_path=f"<synth/{package}>", source_lineno=0,
    )
    return SyntheticPair(nl=nl, atm_line=atm_line, decl=decl)


def _synth_refinement(rng: random.Random, package: str = "synth") -> SyntheticPair:
    """Synthesize an a1 function with a pre/body refinement form.

    v2.6 fix (per swarm code-critic): the atm_line is now produced from
    ``emit_decl`` so it matches what the round-trip parser expects. Previously,
    the atm_line was a hand-folded ``;``-joined form that the parser would have
    treated as structural-fallback rather than refinement form.
    """
    from ..a1_at_functions.atm_emit import emit_decl
    a_name = rng.choice(_VAR_NAMES)
    b_name = rng.choice([v for v in _VAR_NAMES if v != a_name])
    name = rng.choice(["safe_div", "guarded_mul", "checked_sub", "bounded_pow"])
    pre_choices = [f"{b_name}≠0", f"{a_name}≥0", f"{b_name}>0", f"{a_name}≤100"]
    pre = rng.choice(pre_choices)
    op = rng.choice(["+", "-", "*", "/"])
    body = f"{a_name}{op}{b_name}"
    nl = f"Computes {a_name} {op} {b_name}, requires {pre}."
    decl = LoweredDecl(
        tier=1, effect="π", name=name,
        params=[
            LoweredParam(name=a_name, type_sigil="i"),
            LoweredParam(name=b_name, type_sigil="i"),
        ],
        return_sigil="f",
        body_form="refinement", body=body, pre=pre, post="",
        source_path=f"<synth/{package}>", source_lineno=0,
    )
    # Render atm_line directly via the canonical emitter so it round-trips.
    atm_line = emit_decl(decl)
    return SyntheticPair(nl=nl, atm_line=atm_line, decl=decl)


# --- public synthesizer --------------------------------------------------


def generate_synthetic_pairs(
    n: int = 500,
    seed: int = 42,
    weights: dict[str, float] | None = None,
) -> list[SyntheticPair]:
    """Generate `n` synthetic (NL, .atm) pairs.

    `weights` controls the mix of pair kinds. Defaults to a balanced mix
    biased slightly toward the most common shapes (arithmetic, lists).
    """
    rng = random.Random(seed)
    weights = weights or {
        "arith": 0.30,
        "list": 0.25,
        "string": 0.20,
        "record": 0.15,
        "refinement": 0.10,
    }
    synthesizers = {
        "arith": _synth_arith,
        "list": _synth_list,
        "string": _synth_string,
        "record": _synth_record,
        "refinement": _synth_refinement,
    }

    kinds = list(weights.keys())
    cum_weights = []
    total = 0.0
    for k in kinds:
        total += weights[k]
        cum_weights.append(total)

    pairs: list[SyntheticPair] = []
    for _ in range(n):
        r = rng.random() * total
        kind = next(k for k, w in zip(kinds, cum_weights) if r <= w)
        pairs.append(synthesizers[kind](rng))
    return pairs


def synthetic_corpus_lines(pairs: list[SyntheticPair]) -> list[str]:
    """Extract just the .atm lines from synthetic pairs (for BPE training)."""
    return [p["atm_line"] for p in pairs]


def synthetic_decls(pairs: list[SyntheticPair]) -> list[LoweredDecl]:
    """Extract the LoweredDecl from each pair (for collector ingestion)."""
    return [p["decl"] for p in pairs]
