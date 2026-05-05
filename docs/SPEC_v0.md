# `.atm` Surface Grammar — v0

**Scope of this document**: the minimal subset of `.atm` needed to round-trip the Forge calc demo. NOT the full v1 spec. NOT pinned for forward-compatibility. Successors: `SPEC_v0.5.md` after week-1 latency benchmark, `SPEC_v1.md` after `forge raise` (parser direction) lands.

This grammar is what the v0 `forge lower` emitter produces. The companion design rationale lives in [REFINED_DESIGN.md](REFINED_DESIGN.md).

---

## 0 · Lexical structure

### Tier sigils
`0` `1` `2` `3` `4` — digit at the start of a declaration.

| Sigil | Tier name | Imports allowed from | Effects allowed |
|---|---|---|---|
| `0` | `a0_qk_constants` | nothing | `∅` |
| `1` | `a1_at_functions` | `0` | `pure` |
| `2` | `a2_mo_composites` | `0`, `1` | `pure`, `state` |
| `3` | `a3_og_features` | `0..2` | `pure`, `state`, `orch` |
| `4` | `a4_sy_orchestration` | `0..3` | `pure`, `state`, `orch`, `io`, `llm` |

### Effect sigils
Single Unicode glyph following the tier digit. Optional for tier 0.

| Glyph | Effect | ASCII fallback |
|---|---|---|
| `π` | pure | `p` |
| `σ` | state | `s` |
| `ω` | orchestrate | `o` |
| `ι` | io | `i` |
| `λ` | llm | `l` |

The lowerer emits Unicode by default. ASCII fallback exists for environments without UTF-8.

### Type sigils

| Glyph | Type |
|---|---|
| `i` | `int` |
| `f` | `float` |
| `s` | `str` |
| `b` | `bool` |
| `[T]` | list of T |
| `{K:V}` | map K → V |
| `?T` | optional T |
| `T₁→T₂` | function T₁ to T₂ |
| `_` | unknown / inferred |

### Operators (subset for v0)

| Glyph | Meaning | ASCII fallback |
|---|---|---|
| `→` | returns / function arrow | `->` |
| `▷` | pipe | `\|>` |
| `⟨` `⟩` | parameter brackets | `<` `>` |
| `≠` | not equal | `!=` |
| `≥` | greater equal | `>=` |
| `≤` | less equal | `<=` |
| `≟` | equality predicate | `==` |
| `∈` | set membership | `in` |
| `+` `-` `*` `/` | arithmetic (literal) | same |
| `=` | binding | same |
| `!` | raise | same |

### Literals

- Integer: `123`, `-7`
- Float: `1.0`, `-0.5`, `1e-9`
- String: `"…"`
- Bool: `true`, `false`
- Identifier: `[a-z][a-zA-Z0-9_]*`

### Whitespace
Newlines separate declarations. Indentation indicates refinement-block continuation. Spaces within a single declaration are not significant beyond token separation.

---

## 1 · Module structure

```
@<package-name>

<decl>
<decl>
…
```

The `@` line is the package declaration. One per file. Subsequent declarations belong to the package.

---

## 2 · Declaration forms

### 2.1 Constant (tier 0)

```
0 <name> : <type> = <expr>
```

Examples:
```
0 EPS : f = 1e-9
0 PI  : f = 3.14159265
```

### 2.2 Enum (tier 0)

```
0 <name> = enum{<member>, <member>, …}
```

Example:
```
0 OP = enum{+, -, *, /}
```

### 2.3 Pure function (tier 1)

Two body forms.

**Inline**:
```
1π <name> ⟨<param>:<type> <param>:<type> …⟩→<rtype> = <expr>
```

Example:
```
1π add ⟨a:i b:i⟩→i = a+b
```

**Refinement block**:
```
1π <name> ⟨<params>⟩→<rtype>
  pre <expr>
  post <expr>
  body <expr>
```

The `pre` and `post` clauses are optional but at least one of `pre`/`post`/`body` must be present. The `body` clause holds the function body. Within `post`, the bound name `r` refers to the return value.

Example:
```
1π div ⟨a:i b:i⟩→f
  pre b≠0
  body a/b
```

### 2.4 Stateful function (tier 2)

Same shape as tier 1 but with `σ` effect sigil and may declare mutable cell access. v0 emits a literal copy of the Python AST without state-typing analysis (deferred).

### 2.5 Feature orchestrator (tier 3)

Same shape as tier 2 but with `ω` effect sigil. May contain pipe expressions (`▷`).

### 2.6 IO entry point (tier 4)

```
4ι <name> = <body>
```

The body is typically a pipe expression composing argument parsing, dispatch, and output. v0 emits a structural placeholder `<body>` for argparse-style entry points; full lowering of CLI orchestration is deferred.

---

## 3 · Expression grammar (subset for v0)

```
expr  := atom
       | atom op atom
       | call
       | pipe
       | raise
       | branch

atom  := identifier
       | integer-literal
       | float-literal
       | string-literal

op    := '+' | '-' | '*' | '/' | '≠' | '≟' | '≥' | '≤'

call  := identifier '(' arg (',' arg)* ')'

arg   := expr

pipe  := expr '▷' expr     -- left-associative

raise := '!' string-literal

branch := pre-clause -- syntactic sugar; lowers to refinement block
```

This is intentionally tiny. v0 lowers Python's BinOp, Compare, Call, Return, Raise, and the simple `if cond: raise` pattern. Loops, list comprehensions, and complex control flow are not supported in v0.

---

## 4 · Lowering rules (v0)

The `forge lower` tool applies these rules to a tier-organized Python package.

| Python construct | `.atm` lowering |
|---|---|
| Module docstring `"""Tier a1 — …"""` | dropped (info preserved in tier sigil) |
| Function docstring | dropped |
| `def f(a: int, b: int) -> int: return a + b` | `1π f ⟨a:i b:i⟩→i = a+b` |
| `def f(a, b): return a` (no annotations) | `1π f ⟨a:_ b:_⟩→_ = a` |
| `if cond: raise ValueError(msg)` then body | `pre ¬cond ; body <body>` |
| `raise ValueError("…")` | `!"…"` |
| `from pkg.aN_*.foo import foo` | dropped (imports inferred from tier layout) |
| `import argparse` etc. (a4 only) | dropped |
| argparse boilerplate (a4 cli.py) | structural placeholder `4ι <name> = <…>` |

The tier digit is inferred from the path:
- `…/a0_qk_constants/…` → `0`
- `…/a1_at_functions/…` → `1`
- `…/a2_mo_composites/…` → `2`
- `…/a3_og_features/…` → `3`
- `…/a4_sy_orchestration/…` → `4`

The effect sigil is inferred from tier conventionally for v0 (no body analysis):
- tier 0 → no sigil
- tier 1 → `π` (pure)
- tier 2 → `σ` (state)
- tier 3 → `ω` (orch)
- tier 4 → `ι` (io)

A future lowerer (v0.5+) will infer effects from AST analysis.

---

## 5 · Worked example: calc demo

Input (existing Forge output):

```python
# src/calc/a1_at_functions/add.py
"""Tier a1 — pure addition."""

def add(a: int, b: int) -> int:
    """Adds two integers."""
    return a + b
```

Lowered:

```
@calc

1π add ⟨a:i b:i⟩→i = a+b
```

Density: ~30 Python tokens → ~10 .atm tokens (3×). Compounding across 4 a1 functions + tier directory boilerplate = ~6× over the full demo.

---

## 6 · What this spec does NOT cover (deferred)

- Refinement predicate full grammar (only `pre`/`post`/`body` skeleton in v0)
- Type universes, dependent types, Σ-types
- `:llm` effect with FGGM contracts
- Pipe-expression control flow beyond linear chains
- LoRA composition manifest format
- design anchor-Lean refinement obligations citing 578-theorem catalog
- Multi-file linking
- Generics / type variables

These land in v0.5 / v1 after the week-1 falsification benchmark from [REFINED_DESIGN.md §1](REFINED_DESIGN.md).

---

**Status**: v0 spec, draft. Locked enough for the `forge lower` v0 emitter; subject to revision after measured density numbers from the calc-demo lowering.
