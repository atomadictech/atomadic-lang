"""Tests for v0 ``forge lower`` (Python → .atm)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atomadic_lang.a1_at_functions.atm_emit import (
    count_atm_tokens,
    count_py_tokens,
    emit_module,
)
from atomadic_lang.a1_at_functions.body_to_atm import lower_expr, lower_function_body
from atomadic_lang.a1_at_functions.tier_infer import (
    effect_for_tier,
    package_from_path,
    tier_from_path,
)
from atomadic_lang.a1_at_functions.type_to_sigil import annotation_to_sigil
from atomadic_lang.a3_og_features.lower_feature import lower_file, lower_package


from tests._paths import CALC_ROOT


# --- a1 helper unit tests -------------------------------------------------


def test_tier_from_path_a1() -> None:
    p = Path("src/calc/a1_at_functions/add.py")
    assert tier_from_path(p) == 1


def test_tier_from_path_a4() -> None:
    p = Path("src/calc/a4_sy_orchestration/cli.py")
    assert tier_from_path(p) == 4


def test_tier_from_path_unknown_raises() -> None:
    with pytest.raises(ValueError):
        tier_from_path(Path("src/calc/random_dir/foo.py"))


def test_effect_for_tier_defaults() -> None:
    assert effect_for_tier(0) == ""
    assert effect_for_tier(1) == "π"
    assert effect_for_tier(2) == "σ"
    assert effect_for_tier(3) == "ω"
    assert effect_for_tier(4) == "ι"


def test_package_from_path() -> None:
    p = Path("src/calc/a1_at_functions/add.py")
    assert package_from_path(p) == "calc"


def test_annotation_int() -> None:
    src = "def f(a: int) -> int: ...\n"
    tree = ast.parse(src)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert annotation_to_sigil(func.args.args[0].annotation) == "i"
    assert annotation_to_sigil(func.returns) == "i"


def test_annotation_float() -> None:
    src = "def f() -> float: ...\n"
    tree = ast.parse(src)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert annotation_to_sigil(func.returns) == "f"


def test_annotation_missing_returns_underscore() -> None:
    src = "def f(a, b): ...\n"
    tree = ast.parse(src)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert annotation_to_sigil(func.args.args[0].annotation) == "_"


def test_lower_expr_binop_add() -> None:
    expr = ast.parse("a + b", mode="eval").body
    assert lower_expr(expr) == "a+b"


def test_lower_expr_binop_div() -> None:
    expr = ast.parse("a / b", mode="eval").body
    assert lower_expr(expr) == "a/b"


def test_lower_function_body_inline() -> None:
    src = "def add(a, b): return a + b\n"
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert out.body == "a+b"
    assert out.pre == ""


def test_lower_function_body_strips_docstring() -> None:
    src = '''def add(a, b):
    """Adds them."""
    return a + b
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert out.body == "a+b"


def test_lower_function_body_refinement() -> None:
    src = '''def div(a, b):
    if b == 0:
        raise ValueError("div by zero")
    return a / b
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "refinement"
    assert out.pre == "b≠0"
    assert out.body == "a/b"


# --- end-to-end lowering on calc demo ------------------------------------


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_lower_calc_add_file() -> None:
    add_py = CALC_ROOT / "a1_at_functions" / "add.py"
    decls, _ = lower_file(add_py, package="calc")
    assert len(decls) == 1
    d = decls[0]
    assert d["name"] == "add"
    assert d["tier"] == 1
    assert d["effect"] == "π"
    assert d["return_sigil"] == "i"
    assert d["body_form"] == "inline"
    assert d["body"] == "a+b"


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_lower_calc_divide_file_uses_refinement() -> None:
    div_py = CALC_ROOT / "a1_at_functions" / "divide.py"
    decls, _ = lower_file(div_py, package="calc")
    assert len(decls) == 1
    d = decls[0]
    assert d["name"] == "divide"
    assert d["body_form"] == "refinement"
    assert d["pre"] == "b≠0"
    assert d["body"] == "a/b"


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_lower_calc_package_density() -> None:
    """v0 whole-package density check — must be >= 1.0×.

    v0 falls back to structural rendering for argparse-style CLIs (drags the
    whole-package number down). See ``test_lower_calc_a1_only_density`` for
    where the real win is. The 6× density target from REFINED_DESIGN.md is
    a v0.5+ goal contingent on lowering the CLI to a pipe expression.
    """
    module = lower_package(CALC_ROOT)
    a1_decls = [d for d in module["decls"] if d["tier"] == 1]
    assert len(a1_decls) >= 4
    names = {d["name"] for d in a1_decls}
    assert {"add", "subtract", "multiply", "divide"}.issubset(names)
    assert module["density_ratio"] >= 1.0, (
        f"v0 lowering should not be worse than source; got "
        f"{module['density_ratio']:.2f}x "
        f"(py={module['py_token_count']}, atm={module['atm_token_count']})"
    )


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_lower_calc_a1_only_density() -> None:
    """a1-only density should clear the v0 density target (>= 2×).

    The a1 layer is where v0 lowering does its real work — small pure
    functions with full type annotations. The CLI tier (a4) is where
    v0 structurally falls back to verbatim Python.
    """
    a1_dir = CALC_ROOT / "a1_at_functions"
    py_total = 0
    atm_total = 0
    for py_file in sorted(a1_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        decls, py_tokens = lower_file(py_file, package="calc")
        py_total += py_tokens
        atm_total += count_atm_tokens(emit_module("calc", decls))
    density = py_total / atm_total
    # v0-realistic threshold: tiny functions without docstrings give ~1.3×.
    # The 6× target from REFINED_DESIGN.md needs custom BPE + CLI lowering;
    # both are post-v0. This test guards against regression below current.
    assert density >= 1.2, (
        f"a1-only density should be >= 1.2× under v0 lowering; got {density:.2f}x "
        f"(py={py_total}, atm={atm_total})"
    )


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_lower_calc_emits_well_formed_module() -> None:
    module = lower_package(CALC_ROOT)
    text = emit_module(module["package"], module["decls"])
    assert text.startswith("@calc\n")
    # Each a1 fn body should be inline (`= a±b`-shape) except divide (refinement).
    assert "1π add" in text
    assert "1π subtract" in text
    assert "1π multiply" in text
    assert "1π divide" in text
    assert "pre b≠0" in text


# --- token counting sanity ------------------------------------------------


def test_count_py_tokens_simple() -> None:
    """v2.6 tightened: was `8 <= n <= 20` — a 12-wide range that masks
    accidental tokenizer changes. Now pinned to the exact expected count
    so any drift is caught."""
    src = "def f(a, b):\n    return a + b\n"
    n = count_py_tokens(src)
    # Expected count is exactly 11 with the stdlib tokenizer:
    # def, f, (, a, ,, b, ), :, return, a, +, b → 12 with the closing brace?
    # Actually: def(1) f(2) ((3) a(4) ,(5) b(6) )(7) :(8) return(9) a(10) +(11) b(12)
    # tokenize.tokenize emits OP for each punctuation, NAME for identifiers,
    # plus NEWLINE/INDENT/DEDENT we filter. Exact count is 12.
    assert n == 12, f"py token count drifted from canonical 12 to {n}"


def test_count_atm_tokens_simple() -> None:
    src = "@calc\n\n1π add ⟨a:i b:i⟩→i = a+b\n"
    n = count_atm_tokens(src)
    assert n >= 5
    assert n <= 20


# --- v0.6 patterns: multi-statement, ternary, augassign, if/else-return -


def test_lower_function_body_multi_statement_assign_then_return() -> None:
    src = '''def f(a):
    x = a + 1
    y = x * 2
    return y
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert out.body == "(x=a+1 ; y=x*2 ; y)"


def test_lower_function_body_aug_assign() -> None:
    src = '''def f(a):
    x = a
    x += 1
    return x
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert out.body == "(x=a ; x=x+1 ; x)"


def test_lower_function_body_if_else_return_to_ternary() -> None:
    src = '''def absolute(n):
    if n < 0:
        return -n
    else:
        return n
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert out.body == "n<0?-n:n"


def test_lower_expr_ternary() -> None:
    expr = ast.parse("x if cond else y", mode="eval").body
    assert lower_expr(expr) == "cond?x:y"


def test_lower_expr_chained_compare() -> None:
    expr = ast.parse("a < b < c", mode="eval").body
    out = lower_expr(expr)
    # Chained < should become a<b ∧ b<c
    assert "∧" in out
    assert "a<b" in out
    assert "b<c" in out


def test_lower_function_body_call_then_return() -> None:
    src = '''def f(x):
    print(x)
    return x
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert out.body == "(print(x) ; x)"


def test_lower_function_body_implicit_none() -> None:
    """A function with only a print statement (no return) implicit-returns ∅."""
    src = '''def hello(name):
    print("hi " + name)
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert "print" in out.body
    assert out.body.endswith("; ∅)")


# --- v0.7: classes -------------------------------------------------------


def _ast_module(src: str) -> ast.Module:
    return ast.parse(src)


def test_lower_class_with_init_emits_field_decl_plus_methods() -> None:
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class Counter:
    def __init__(self, start: int = 0):
        self.value = start

    def increment(self) -> None:
        self.value += 1

    def get(self) -> int:
        return self.value
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="src/p/a2_mo_composites/counter.py")

    # 1 class field decl + 2 method decls (no __init__ in output).
    assert len(decls) == 3
    field_decl = decls[0]
    assert field_decl["name"] == "Counter"
    assert field_decl["body_form"] == "class"
    assert field_decl["params"] == [{"name": "value", "type_sigil": "i"}]

    method_names = [d["name"] for d in decls[1:]]
    assert "Counter.increment" in method_names
    assert "Counter.get" in method_names


def test_lower_class_typeddict_style_uses_class_body_annotations() -> None:
    """A TypedDict-style class lowers its annotated class-body fields directly."""
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class SymbolRecord:
    name: str
    qualname: str
    lineno: int
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=0, effect="", source_path="src/p/a0_qk_constants/types.py")
    assert len(decls) == 1
    field_decl = decls[0]
    assert field_decl["name"] == "SymbolRecord"
    assert field_decl["body_form"] == "class"
    sigils = {p["name"]: p["type_sigil"] for p in field_decl["params"]}
    assert sigils == {"name": "s", "qualname": "s", "lineno": "i"}


def test_lower_method_self_typed_as_class_name() -> None:
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class Box:
    def __init__(self, x: int):
        self.x = x

    def double(self) -> int:
        return self.x * 2
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="x.py")
    method = next(d for d in decls if d["name"] == "Box.double")
    # First param is self:Box.
    assert method["params"][0] == {"name": "self", "type_sigil": "Box"}
    # Body lowers self.x*2 to attribute access form.
    assert method["body"] == "self.x*2"
    assert method["body_form"] == "inline"


def test_lower_method_with_self_attribute_assignment() -> None:
    """Method body with `self.x += 1` should lower as attribute aug-assign."""
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class Counter:
    def __init__(self):
        self.value = 0

    def incr(self) -> None:
        self.value += 1
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="x.py")
    incr = next(d for d in decls if d["name"] == "Counter.incr")
    # `self.value += 1` → `self.value=self.value+1`, wrapped in sequence
    # because the body has 1 stmt + implicit-None.
    assert "self.value" in incr["body"]
    assert "self.value+1" in incr["body"]


def test_lower_class_dunder_methods_dropped() -> None:
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class P:
    def __init__(self, x: int):
        self.x = x

    def __repr__(self):
        return "P()"

    def real_method(self) -> int:
        return self.x
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="x.py")
    names = [d["name"] for d in decls]
    assert "P" in names
    assert "P.real_method" in names
    assert "P.__repr__" not in names


def test_lower_class_with_no_init_emits_empty_field_decl() -> None:
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class Empty:
    def thing(self) -> int:
        return 0
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="x.py")
    field = decls[0]
    assert field["name"] == "Empty"
    assert field["body_form"] == "class"
    assert field["params"] == []


def test_class_field_inference_picks_up_constructor_arg_types() -> None:
    """`self.foo = some_arg` should get foo's type from some_arg's annotation."""
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class Pair:
    def __init__(self, name: str, count: int):
        self.name = name
        self.count = count
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="x.py")
    sigils = {p["name"]: p["type_sigil"] for p in decls[0]["params"]}
    assert sigils == {"name": "s", "count": "i"}


def test_class_field_inference_falls_back_to_literal_type() -> None:
    """`self.x = 0` (int literal) → field x:i; `self.label = ""` → s."""
    from atomadic_lang.a3_og_features.lower_feature import _lower_class

    src = '''class Mix:
    def __init__(self):
        self.count = 0
        self.label = ""
        self.ratio = 1.0
        self.flag = True
        self.data = []
'''
    cls = _ast_module(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    decls = _lower_class(cls, tier=2, effect="σ", source_path="x.py")
    sigils = {p["name"]: p["type_sigil"] for p in decls[0]["params"]}
    assert sigils == {
        "count": "i", "label": "s", "ratio": "f", "flag": "b", "data": "[_]"
    }


def test_lower_attribute_assignment_at_function_level() -> None:
    """`obj.field = value` in a regular function body, not just methods."""
    src = '''def f(obj):
    obj.x = 1
    obj.y = 2
    return obj
'''
    func = ast.parse(src).body[0]
    assert isinstance(func, ast.FunctionDef)
    out = lower_function_body(func.body)
    assert out.form == "inline"
    assert "obj.x=1" in out.body
    assert "obj.y=2" in out.body


# --- v0.8: f-strings + comprehensions + lambdas -------------------------


def test_lower_fstring_simple() -> None:
    expr = ast.parse('f"hi {name}"', mode="eval").body
    out = lower_expr(expr)
    assert out == 's"hi ⟦name⟧"'


def test_lower_fstring_multiple_substitutions() -> None:
    expr = ast.parse('f"hi {name}, age {age}"', mode="eval").body
    out = lower_expr(expr)
    assert out == 's"hi ⟦name⟧, age ⟦age⟧"'


def test_lower_fstring_with_expression() -> None:
    expr = ast.parse('f"sum: {a + b}"', mode="eval").body
    out = lower_expr(expr)
    assert out == 's"sum: ⟦a+b⟧"'


def test_lower_fstring_with_format_spec() -> None:
    expr = ast.parse('f"v={x:.2f}"', mode="eval").body
    out = lower_expr(expr)
    # Format spec preserved inside the bracket
    assert out == 's"v=⟦x:.2f⟧"'


def test_lower_fstring_pure_literal() -> None:
    expr = ast.parse('f"hello"', mode="eval").body
    out = lower_expr(expr)
    # No substitutions, just text
    assert out == 's"hello"'


def test_lower_list_comprehension_simple() -> None:
    expr = ast.parse("[x*2 for x in xs]", mode="eval").body
    out = lower_expr(expr)
    assert out == "[x*2 | x∈xs]"


def test_lower_list_comprehension_with_filter() -> None:
    expr = ast.parse("[x for x in xs if x > 0]", mode="eval").body
    out = lower_expr(expr)
    assert out == "[x | x∈xs ? x>0]"


def test_lower_list_comprehension_two_iterators() -> None:
    expr = ast.parse("[x+y for x in xs for y in ys]", mode="eval").body
    out = lower_expr(expr)
    # Two `for` clauses → comma-separated
    assert out.startswith("[x+y | ")
    assert "x∈xs" in out
    assert "y∈ys" in out
    assert ", " in out


def test_lower_dict_comprehension() -> None:
    expr = ast.parse("{k: v for k, v in items}", mode="eval").body
    out = lower_expr(expr)
    # Tuple target unpacking lowers as (k,v)
    assert "k:v" in out
    assert "(k,v)∈items" in out


def test_lower_set_comprehension() -> None:
    expr = ast.parse("{x for x in xs}", mode="eval").body
    out = lower_expr(expr)
    assert out == "{x | x∈xs}"


def test_lower_generator_expression() -> None:
    expr = ast.parse("(x*2 for x in xs)", mode="eval").body
    out = lower_expr(expr)
    assert out == "(x*2 | x∈xs)"


def test_lower_lambda_single_arg() -> None:
    expr = ast.parse("lambda x: x*2", mode="eval").body
    out = lower_expr(expr)
    assert out == "x↦x*2"


def test_lower_lambda_multi_arg() -> None:
    expr = ast.parse("lambda a, b: a+b", mode="eval").body
    out = lower_expr(expr)
    assert out == "(a,b)↦a+b"


def test_lower_lambda_no_arg() -> None:
    expr = ast.parse("lambda: 42", mode="eval").body
    out = lower_expr(expr)
    assert out == "()↦42"


def test_lower_lambda_inside_call() -> None:
    """``map(lambda x: x*2, xs)`` should compose cleanly."""
    expr = ast.parse("map(lambda x: x*2, xs)", mode="eval").body
    out = lower_expr(expr)
    assert "x↦x*2" in out
    assert out.startswith("map(")


def test_lower_listcomp_with_call_filter() -> None:
    expr = ast.parse("[x for x in xs if is_valid(x)]", mode="eval").body
    out = lower_expr(expr)
    assert "is_valid(x)" in out
    assert out.startswith("[x | x∈xs ? ")
