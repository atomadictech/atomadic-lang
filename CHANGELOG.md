# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows semantic
versioning while it is pre-alpha.

## [3.4.0] - 2026-05-05

### Added

- **Property-based round-trip fuzzer** —
  `tests/test_property_roundtrip.py` uses Hypothesis to generate
  randomised function bodies in the supported lowering subset and
  asserts the byte-identical round-trip invariant
  `lower → emit → parse → re-emit == emit` across thousands of cases.
- 7 fuzzer strategies covering every recognised inline body form:
  - **Inline `BinOp`** (`return a±b`) — 300 cases
  - **Inline ternary** (`return t if cond else f`) — 300 cases
  - **Refinement** (`if cond: raise ValueError(...); return ...`) — 200 cases
  - **Sequence** (`var = a±b; return var`) — 200 cases
  - **`match`/`case` literal** (1–4 distinct int cases + wildcard) — 300 cases
  - **`match`/`case` OR-pattern** (2–4-arity disjunction + wildcard) — 200 cases
  - **F-string** single-substitution — 200 cases
- ~1,800 randomised cases per `pytest` run, all property-passing.
- The new v3.3 `match`/`case` lowering is fuzzed from day one through
  Strategies 5 and 6.

### Dependencies

- `[project.optional-dependencies] dev` adds `hypothesis>=6.100`. No
  runtime dependency change.

### Tests

- 337 → **344 passed** (+7 property strategies, each a single test that
  runs 200–300 inner cases), 2 xfailed unchanged.
- ruff clean. Wall clock ≈ 9.7 s including ~1,800 fuzz cases.

### Notes

- Strategies use the same 8-int-parameter signature
  (`a, b, c, x, y, n, k, m`) so generated bodies never reference an
  unbound name. F-string strategy generates lowercase-only string
  segments to keep the inner content within the supported character
  class.
- All strategies converge on the inline / refinement form before the
  round-trip check; bodies that hit the structural fallback are rare
  given the construction and are skipped via `pytest.skip` when
  encountered (only the f-string strategy can hit this in practice
  given the existing lowering coverage).

## [3.3.0] - 2026-05-05

### Added

- **`match`/`case` body-form lowering.** Python 3.10+ `match` statements
  now lower to nested ternary expressions in `.atm` rather than falling
  through to the structural placeholder. Two new helpers in
  `a1/body_to_atm.py`:
  - `_match_to_ternary(match_node)` — walks the match cases, builds a
    right-associative ternary chain. Returns `None` (→ structural
    fallback) if any case is unsupported.
  - `_pattern_to_test(pattern, subject)` — lowers a single match
    pattern to a test expression against the subject.
- Supported case-pattern shapes:
  - `MatchValue` (literals): `case 1:`, `case "yes":` → `subject≟<lit>`
  - `MatchSingleton`: `case None:` → `subject≟∅`; `case True/False:`
    → `subject≟true` / `subject≟false`
  - `MatchOr`: `case 1 | 2 | 3:` → `subject≟1∨subject≟2∨subject≟3`
  - `MatchAs(None, None)` (wildcard `case _:`) → fallthrough else branch
- Unsupported patterns (`MatchAs(name=...)` capture, `MatchClass`,
  `MatchSequence`, `MatchMapping`, `MatchStar`, guarded cases) cause
  the lowerer to return `None`, triggering the structural placeholder
  fallback. The lowerer is total — no input is rejected.
- Match expressions without a wildcard branch fall back to structural,
  preserving the totality invariant (the resulting ternary would be
  partial without a default).
- 11 new unit tests in `tests/test_lower.py` covering literal-int,
  string-literal, `None`/`True`/`False` singleton, OR-pattern,
  two-case minimum, no-wildcard fallback, guard fallback, capture
  fallback, class-pattern fallback, and **byte-identical round-trip**
  (`emit → parse → re-emit == original`) on a representative
  multi-case match.

### Tests

- 326 → **337 passed** (+11), 2 xfailed unchanged.
- `forge wire` 0 violations, ruff clean.

### Notes

- Lowering preserves left-to-right case ordering: the first matching
  case wins, exactly as Python's match semantics specify.
- Right-associative parenthesisation: nested ternaries
  `t1?b1:(t2?b2:default)` keep the false-branch parsed unambiguously
  by the existing `cond?a:b` parser.

## [3.2.0] - 2026-05-05

### Added

- **Path A.3 — W-grammar classifier coverage for encoding noise + Python
  dunders.** Two new legal token roles in `a0/wgrammar.py`:
  - `ENCODING_NOISE` — recognises tokens that are entirely encoding
    artifacts: replacement char `�`, non-breaking space, zero-width
    space / non-joiner / joiner, line separator, paragraph separator,
    BOM. These show up in real corpora when source files cross
    encoding boundaries (Windows cp1252 → UTF-8 round-trips, etc.) and
    have no structural meaning. Classifying them as legal-but-noisy
    keeps them out of the `UNKNOWN` overfit signal where they would
    otherwise dominate.
  - `DUNDER` — recognises Python double-underscore identifiers
    (`__init__`, `__main__`, `__name__`, `__class__`, `__repr__`) and
    bare runs (`__`, `___`, `____`). Pattern dispatch order puts
    `DUNDER` before `IDENT_FRAG` so `__init__` is correctly classified
    as a dunder rather than a generic identifier fragment; single-
    underscore identifiers like `_init` and `init_` continue to
    classify as `IDENT_FRAG`.
- 13 new unit tests covering the new role coverage; total test count
  311 → 326.

### Changed

- `wgrammar.py` module docstring stripped of stale references; classifier
  documentation now describes the role lattice without referring to
  any specific corpus / hold-out finding.

## [3.1.0] - 2026-05-05

Pre-alpha verified IR for AI-emitted code. Snapshot release after a
thorough internal cleanup pass.

### Components

- 5-tier monadic source layout (`a0_qk_constants` … `a4_sy_orchestration`)
  with upward-only import discipline.
- Python → `.atm` lowering, `.atm` parser, byte-identical round-trip,
  custom 4096-vocab BPE tokenizer.
- W-grammar audit + enforcement gate with anchored overfit threshold
  (`OVERFIT_BOUND_DEFAULT = 3 / 1823 ≈ 0.001646`). The gate exits
  non-zero when a tokenizer's overfit fraction exceeds the bound.
- W-grammar classifier covers structural, expression, escape, call-site,
  and parameter-tag token shapes.
- Self-contained calc fixture under `tests/fixtures/calc/`; the test
  suite no longer depends on any external sibling repo.
- Portfolio merge-audit primitive (`tools/merge_audit.py`) that mirrors
  N tier-organized Python packages into a fresh tempdir, runs `forge`
  + `atomadic-lang` diagnostics on the merged super-package, and emits
  a unified JSON report.

### Anchored design constants

A small a0 lookup table (`design_anchors.py`) names a few numerical
anchors used as gate thresholds and verification bounds:
`OVERFIT_BOUND_DEFAULT`, `DELEGATION_DEPTH_LIMIT`, `KL_DIVERGENCE_BOUND`,
`HIERARCHY_FACTOR`, `SEMANTIC_FRICTION_LIMIT`, `IDENTITY_RESIDUE`,
`ANCHORED_VOCAB_SIZE`. Values are public mathematical anchors;
specific provenance commentary lives in private design notes.

### Toolchain

- CLI: `atomadic-lang lower` / `raise` / `roundtrip` / `tokenize` /
  `density` / `benchmark` / `wgrammar-audit` / `version`.
- `wgrammar-audit --enforce` adds a binding gate; `--max-overfit`
  overrides the anchored default.
- `lower_package()` resilient to per-file `ast.parse` failures so
  real-world corpora with in-progress files don't abort the walk.

### Tests + gates

- Multi-language pytest suite covers every public surface.
- `python -m ruff check .` is clean.
- `forge wire src --fail-on-violations` reports 0 violations.
- `forge certify .` runs the full release roll-up.
