# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog, and this project follows semantic
versioning while it is pre-alpha.

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
