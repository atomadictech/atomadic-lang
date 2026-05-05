"""Tests for v1.0 ``forge raise`` (`.atm` → LoweredDecl[]).

Verifies the round-trip property:
    lower(py) → emit_module → parse_module → emit_module == original_emit
"""

from __future__ import annotations

import pytest

from atomadic_lang.a1_at_functions.atm_emit import emit_module
from atomadic_lang.a1_at_functions.atm_parse import (
    parse_decl,
    parse_module,
)
from atomadic_lang.a3_og_features.lower_feature import lower_file, lower_package
from atomadic_lang.a3_og_features.raise_feature import (
    raise_atm_text,
    roundtrip_decls,
)


from tests._paths import CALC_ROOT, FORGE_ROOT


# --- single-decl parse cases --------------------------------------------


def test_parse_decl_inline_simple() -> None:
    d = parse_decl("1π add ⟨a:i b:i⟩→i = a+b")
    assert d is not None
    assert d["tier"] == 1
    assert d["effect"] == "π"
    assert d["name"] == "add"
    assert d["return_sigil"] == "i"
    assert d["body_form"] == "inline"
    assert d["body"] == "a+b"
    assert d["params"] == [
        {"name": "a", "type_sigil": "i"},
        {"name": "b", "type_sigil": "i"},
    ]


def test_parse_decl_no_params() -> None:
    d = parse_decl("4ι main ⟨⟩→_ = body_expr")
    assert d is not None
    assert d["tier"] == 4
    assert d["effect"] == "ι"
    assert d["name"] == "main"
    assert d["params"] == []
    assert d["return_sigil"] == "_"
    assert d["body"] == "body_expr"


def test_parse_decl_refinement_form() -> None:
    head = "1π divide ⟨a:i b:i⟩→f"
    cont = ["  pre b≠0", "  body a/b"]
    d = parse_decl(head, cont)
    assert d is not None
    assert d["body_form"] == "refinement"
    assert d["pre"] == "b≠0"
    assert d["body"] == "a/b"
    assert d["return_sigil"] == "f"


def test_parse_decl_refinement_with_post() -> None:
    head = "1π div ⟨a:i b:i⟩→f"
    cont = ["  pre b≠0", "  post r·b≈a", "  body a/b"]
    d = parse_decl(head, cont)
    assert d is not None
    assert d["pre"] == "b≠0"
    assert d["post"] == "r·b≈a"
    assert d["body"] == "a/b"


def test_parse_decl_class_form() -> None:
    d = parse_decl("2σ Counter ⟨value:i⟩")
    assert d is not None
    assert d["tier"] == 2
    assert d["effect"] == "σ"
    assert d["name"] == "Counter"
    assert d["body_form"] == "class"
    assert d["body"] == ""
    assert d["params"] == [{"name": "value", "type_sigil": "i"}]


def test_parse_decl_class_form_typeddict() -> None:
    d = parse_decl(
        "0 ScoutReport ⟨schema_version:s repo:s file_count:i symbols:[_]⟩"
    )
    assert d is not None
    assert d["tier"] == 0
    assert d["effect"] == ""
    assert d["name"] == "ScoutReport"
    assert d["body_form"] == "class"
    assert {p["name"] for p in d["params"]} == {
        "schema_version", "repo", "file_count", "symbols"
    }


def test_parse_decl_tier0_const() -> None:
    d = parse_decl("0 EPS : f = 1e-9")
    assert d is not None
    assert d["tier"] == 0
    assert d["name"] == "EPS"
    assert d["return_sigil"] == "f"
    assert d["body"] == "1e-9"


def test_parse_decl_dotted_method_name() -> None:
    d = parse_decl("2σ Counter.increment ⟨self:Counter⟩→∅ = (self.value=self.value+1 ; ∅)")
    assert d is not None
    assert d["name"] == "Counter.increment"
    assert d["params"] == [{"name": "self", "type_sigil": "Counter"}]
    assert d["return_sigil"] == "∅"
    assert "self.value" in d["body"]


def test_parse_module_simple() -> None:
    text = (
        "@calc\n"
        "\n"
        "1π add ⟨a:i b:i⟩→i = a+b\n"
        "1π subtract ⟨a:i b:i⟩→i = a-b\n"
    )
    mod = parse_module(text)
    assert mod["package"] == "calc"
    assert len(mod["decls"]) == 2
    assert mod["decls"][0]["name"] == "add"
    assert mod["decls"][1]["name"] == "subtract"


def test_parse_module_with_refinement() -> None:
    text = (
        "@calc\n\n"
        "1π add ⟨a:i b:i⟩→i = a+b\n"
        "1π divide ⟨a:i b:i⟩→f\n"
        "  pre b≠0\n"
        "  body a/b\n"
        "1π multiply ⟨a:i b:i⟩→i = a*b\n"
    )
    mod = parse_module(text)
    assert len(mod["decls"]) == 3
    div = mod["decls"][1]
    assert div["name"] == "divide"
    assert div["body_form"] == "refinement"
    assert div["pre"] == "b≠0"
    assert div["body"] == "a/b"


def test_raise_atm_text_alias() -> None:
    text = "@x\n\n1π f ⟨⟩→_ = ∅\n"
    mod = raise_atm_text(text)
    assert mod["package"] == "x"
    assert mod["decls"][0]["name"] == "f"


# --- round-trip property tests ------------------------------------------


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_roundtrip_calc_demo() -> None:
    """``lower(calc) → emit → parse → emit`` should produce identical text."""
    module = lower_package(CALC_ROOT)
    report = roundtrip_decls(module["decls"], package="calc")
    assert report["text_identical"], (
        f"Roundtrip mismatch at char {report['diff_first_chars']}:\n"
        f"{report['sample_diff']}"
    )
    assert report["decl_count_match"]


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_roundtrip_calc_a1_only() -> None:
    """Just the a1 functions (most common case)."""
    decls = []
    for fname in ("add.py", "subtract.py", "multiply.py", "divide.py"):
        d, _ = lower_file(CALC_ROOT / "a1_at_functions" / fname, package="calc")
        decls.extend(d)
    report = roundtrip_decls(decls, package="calc")
    assert report["text_identical"], (
        f"a1-only roundtrip mismatch at char {report['diff_first_chars']}:\n"
        f"{report['sample_diff']}"
    )


@pytest.mark.skipif(not FORGE_ROOT.exists(), reason="atomadic-forge source not present")
def test_roundtrip_forge_corpus() -> None:
    """Round-trip all of atomadic-forge: must be byte-identical."""
    module = lower_package(FORGE_ROOT)
    report = roundtrip_decls(module["decls"], package=module["package"])
    if not report["text_identical"]:
        # Print a window into the divergence and fail with the diagnostic.
        pytest.fail(
            f"Forge corpus roundtrip mismatch at char {report['diff_first_chars']}:\n"
            f"{report['sample_diff']}"
        )


# --- raise → re-lower equivalence on representative shapes ---------------


def test_class_form_roundtrip() -> None:
    text = (
        "@p\n\n"
        "2σ Counter ⟨value:i⟩\n"
        "2σ Counter.get ⟨self:Counter⟩→i = self.value\n"
        "2σ Counter.increment ⟨self:Counter⟩→∅ = (self.value=self.value+1 ; ∅)\n"
    )
    mod = parse_module(text)
    re_text = emit_module(mod["package"], mod["decls"])
    assert re_text == text


def test_typeddict_roundtrip() -> None:
    text = (
        "@p\n\n"
        "0 SymbolRecord ⟨name:s qualname:s lineno:i⟩\n"
    )
    mod = parse_module(text)
    re_text = emit_module(mod["package"], mod["decls"])
    assert re_text == text


def test_refinement_roundtrip() -> None:
    text = (
        "@p\n\n"
        "1π divide ⟨a:i b:i⟩→f\n"
        "  pre b≠0\n"
        "  body a/b\n"
    )
    mod = parse_module(text)
    re_text = emit_module(mod["package"], mod["decls"])
    assert re_text == text


def test_inline_with_complex_body_roundtrip() -> None:
    text = (
        "@p\n\n"
        '1π render ⟨name:s⟩→s = s"hello ⟦name⟧"\n'
    )
    mod = parse_module(text)
    re_text = emit_module(mod["package"], mod["decls"])
    assert re_text == text
