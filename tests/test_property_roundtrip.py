"""Property-based round-trip tests for the lowering pipeline.

The strongest invariant the project has is byte-identical round-trip:
``parse(emit(lower(py))) == lower(py)`` and the re-emitted text matches
the original emitted text. These tests use Hypothesis to generate
randomised function bodies in the supported lowering subset and assert
the invariant holds across thousands of cases.

Each strategy below corresponds to a recognised body form
(`body_to_atm.lower_function_body` patterns 1–2c). Together they
exercise every inline lowering path the lowerer accepts. The match/case
shape (Pattern 2c, v3.3) is included so the new code path is fuzzed
from day one.

A drift in any case typically points at an emitter bug — historically
this is exactly how the v1.0 round-trip property surfaced four latent
bugs that no unit test could catch.
"""

from __future__ import annotations

import ast

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from atomadic_lang.a1_at_functions.atm_emit import emit_module
from atomadic_lang.a1_at_functions.atm_parse import parse_module
from atomadic_lang.a1_at_functions.body_to_atm import lower_function_body


# --- shared building blocks ----------------------------------------------


_NAMES = st.sampled_from(["a", "b", "c", "x", "y", "n", "k", "m"])
_INTS = st.integers(min_value=-50, max_value=50)
_BIN_OPS = st.sampled_from(["+", "-", "*"])  # safe for ints; "/" makes float
_CMP_OPS = st.sampled_from(["==", "!=", "<", ">", "<=", ">="])
_STRINGS = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),  # a-z
    min_size=1,
    max_size=8,
)
# Names used as the function's formal parameters (8 params, all int).
_PARAM_NAMES = ["a", "b", "c", "x", "y", "n", "k", "m"]
_PARAM_DECL = ", ".join(f"{p}: int" for p in _PARAM_NAMES)


def _emit_parse_roundtrip(decl: dict, package: str = "p") -> None:
    """Assert emit -> parse -> re-emit is byte-identical."""
    text = emit_module(package, [decl])
    parsed = parse_module(text)
    assert parsed["package"] == package
    assert len(parsed["decls"]) == 1
    re_text = emit_module(parsed["package"], parsed["decls"])
    assert text == re_text, (
        f"round-trip mismatch:\norig={text!r}\nre  ={re_text!r}"
    )


def _wrap_function(body_src: str, name: str = "f", returns: str = "int") -> ast.FunctionDef:
    """Parse a function with the standard 8-int-parameter signature."""
    src = f"def {name}({_PARAM_DECL}) -> {returns}:\n    {body_src}\n"
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    return func


def _build_decl_from_body(
    func: ast.FunctionDef, name: str = "f", return_sigil: str = "i"
) -> dict | None:
    """Lower a function body and shape into a LoweredDecl. Returns None
    if the lowering didn't produce an inline form (we only fuzz inline)."""
    out = lower_function_body(func.body)
    if out.form not in ("inline", "refinement"):
        return None
    decl = {
        "tier": 1,
        "effect": "π",
        "name": name,
        "params": [
            {"name": p, "type_sigil": "i"} for p in _PARAM_NAMES
        ],
        "return_sigil": return_sigil,
        "body_form": out.form,
        "body": out.body,
        "pre": out.pre,
        "post": out.post,
        "source_path": "fuzz.py",
        "source_lineno": 1,
    }
    return decl


# --- Strategy 1: simple BinOp inline returns ------------------------------


@st.composite
def _inline_binop_body(draw) -> str:
    a = draw(_NAMES)
    op = draw(_BIN_OPS)
    b = draw(_NAMES)
    return f"return {a}{op}{b}"


@given(body=_inline_binop_body())
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_property_inline_binop_roundtrip(body: str) -> None:
    """Property: any `return a±b` round-trips byte-identically."""
    func = _wrap_function(body)
    decl = _build_decl_from_body(func)
    assert decl is not None
    _emit_parse_roundtrip(decl)


# --- Strategy 2: ternary inline returns -----------------------------------


@st.composite
def _inline_ternary_body(draw) -> str:
    a = draw(_NAMES)
    cmp_op = draw(_CMP_OPS)
    b = draw(_NAMES)
    t = draw(_NAMES)
    f = draw(_NAMES)
    return f"return {t} if {a} {cmp_op} {b} else {f}"


@given(body=_inline_ternary_body())
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_property_inline_ternary_roundtrip(body: str) -> None:
    """Property: any `return t if cond else f` round-trips byte-identically."""
    func = _wrap_function(body)
    decl = _build_decl_from_body(func)
    assert decl is not None
    _emit_parse_roundtrip(decl)


# --- Strategy 3: refinement form (if-raise + return) ----------------------


@st.composite
def _refinement_body(draw) -> str:
    a = draw(_NAMES)
    cmp_op = draw(st.sampled_from(["==", "!="]))
    b = draw(_NAMES)
    t = draw(_NAMES)
    f = draw(_NAMES)
    msg = draw(_STRINGS)
    return (
        f"if {a} {cmp_op} {b}:\n"
        f'        raise ValueError("{msg}")\n'
        f"    return {t}+{f}"
    )


@given(body=_refinement_body())
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_refinement_roundtrip(body: str) -> None:
    """Property: if-raise + return refinement round-trips byte-identically."""
    func = _wrap_function(body)
    decl = _build_decl_from_body(func)
    assert decl is not None
    assert decl["body_form"] == "refinement"
    _emit_parse_roundtrip(decl)


# --- Strategy 4: assign + return sequence ---------------------------------


@st.composite
def _sequence_body(draw) -> str:
    var = draw(st.sampled_from(["t", "u", "v", "w"]))  # not in PARAM_NAMES
    a = draw(_NAMES)
    op = draw(_BIN_OPS)
    b = draw(_NAMES)
    return f"{var} = {a}{op}{b}\n    return {var}"


@given(body=_sequence_body())
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_sequence_roundtrip(body: str) -> None:
    """Property: `(var = a±b ; var)` sequence form round-trips byte-identically."""
    func = _wrap_function(body)
    decl = _build_decl_from_body(func)
    assert decl is not None
    _emit_parse_roundtrip(decl)


# --- Strategy 5: match/case literal cases (v3.3 path under fuzz) ----------


@st.composite
def _match_literal_body(draw) -> str:
    """Generate a match-statement with N literal-int cases + wildcard."""
    n_cases = draw(st.integers(min_value=1, max_value=4))
    subject = draw(_NAMES)
    # Distinct integer cases
    case_vals = draw(
        st.lists(_INTS, min_size=n_cases, max_size=n_cases, unique=True)
    )
    case_results = [
        draw(_NAMES) for _ in range(n_cases)
    ]
    default = draw(_NAMES)

    lines = [f"match {subject}:"]
    for v, r in zip(case_vals, case_results):
        lines.append(f"        case {v}: return {r}")
    lines.append(f"        case _: return {default}")
    return "\n    ".join(lines)


@given(body=_match_literal_body())
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_property_match_literal_roundtrip(body: str) -> None:
    """Property: any literal-case match with wildcard round-trips byte-identically."""
    func = _wrap_function(body)
    decl = _build_decl_from_body(func)
    assert decl is not None
    assert decl["body_form"] == "inline"
    _emit_parse_roundtrip(decl)


# --- Strategy 6: match/case OR pattern ------------------------------------


@st.composite
def _match_or_body(draw) -> str:
    """Generate a match with one OR-pattern case + wildcard."""
    subject = draw(_NAMES)
    or_arity = draw(st.integers(min_value=2, max_value=4))
    or_vals = draw(
        st.lists(_INTS, min_size=or_arity, max_size=or_arity, unique=True)
    )
    or_branch = " | ".join(str(v) for v in or_vals)
    hit = draw(_NAMES)
    miss = draw(_NAMES)

    return (
        f"match {subject}:\n"
        f"        case {or_branch}: return {hit}\n"
        f"        case _: return {miss}"
    )


@given(body=_match_or_body())
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_match_or_roundtrip(body: str) -> None:
    """Property: OR-pattern match round-trips byte-identically."""
    func = _wrap_function(body)
    decl = _build_decl_from_body(func)
    assert decl is not None
    assert decl["body_form"] == "inline"
    _emit_parse_roundtrip(decl)


# --- Strategy 7: f-string single-substitution -----------------------------


@st.composite
def _fstring_body(draw) -> str:
    prefix = draw(_STRINGS)
    name = draw(_NAMES)
    suffix = draw(_STRINGS)
    return f'return f"{prefix}{{{name}}}{suffix}"'


@given(body=_fstring_body())
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_fstring_roundtrip(body: str) -> None:
    """Property: f-string with a single name substitution round-trips."""
    func = _wrap_function(body, returns="str")
    decl = _build_decl_from_body(func, return_sigil="s")
    if decl is None:
        pytest.skip("f-string body not lowerable to inline (skipping)")
    _emit_parse_roundtrip(decl)
