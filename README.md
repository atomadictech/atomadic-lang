# Atomadic Lang (`.atm`) — Verified IR for AI-Emitted Code

Part of the **Atomadic portfolio**: Atomadic Lang is the verification and
compression layer for sovereign AI systems, complementing **Atomadic**,
**Atomadic Forge**, and **AAAA-Nexus**.

> **`.atm` is a verified intermediate representation for AI-emitted code, not a source language.** The relationship to surface code (Python, eventually JS/Rust/etc.) is the same as `wat` to `wasm`, or `.proto` to protobuf: humans author in a familiar surface, the toolchain compiles to a dense, structurally-verified, edge-deployable IR. The IR is what gets stored, transmitted, masked at decode time, and verified.

**Status**: v2.6 (post-swarm-audit pivot). 11 milestones shipped in one session, then a 4-critic hostile review forced a reframing and 9 critical bug fixes.

---

## What this is

A runnable system for:

| Capability | Command | What it does |
|---|---|---|
| Lower Python → `.atm` | `python -m atomadic_lang lower <pkg>` | Compile a tier-organized Python package into the dense `.atm` IR |
| Train custom BPE | `python -m atomadic_lang tokenize <pkgs> -o tokenizer.json` | Build a 4096-vocab BPE specialized to the IR |
| Parse `.atm` → AST | `python -m atomadic_lang raise <atm-file>` | Inverse of `lower` — recover `LoweredDecl[]` from text |
| Verify round-trip | `python -m atomadic_lang roundtrip <atm-file>` | Check `parse + re-emit == original` byte-identically |
| Measure density | `python -m atomadic_lang density <py> <atm> -t <tokenizer>` | Compare cl100k tokens vs `.atm` BPE tokens |
| Run §1 latency benchmark | `python -m atomadic_lang benchmark -t tokenizer.json` | Mask + state + refinement + logit-application timing |

## Why "IR, not source language"

The original framing — "AI-author programming language" — survived 10 milestones and a hostile architecture review told us it was wrong. Three independent critics converged on: humans **do** read `.atm` (errors, debug logs, code review), AI authors do **not** yet emit it (no model has been trained), and the empirical claims compare `.atm` against general-purpose tokenizers in ways that only make sense if `.atm` is positioned as IR.

Reframing as IR makes every other architectural choice well-motivated:

- **Custom 4096-token BPE** is appropriate (every binary IR has a custom encoding).
- **Tier sigils eating 2 bits of the vocabulary** is appropriate (IRs structure their opcodes).
- **Dense, machine-first surface** is appropriate (humans interact with the source language; `.atm` is what gets stored).
- **Byte-identical round-trip property** is the natural IR invariant.
- **Sub-microsecond mask evaluator** is appropriate (IRs are processed at line rate).
- **Edge-deployable** is appropriate (IRs are loaded everywhere the system runs).

The IR is what goes between the source-language compiler and the runtime. AI authors edit Python (or whatever rich surface); the toolchain compiles to `.atm`; runtime executes (or verifies, or transmits) the IR. Humans never have to read `.atm` directly any more than they read object files.

## Empirical results (v2.6 — re-measured under corrected methodology)

These numbers are after the v2.6 audit pass that fixed the four critical methodology bugs the swarm review identified:

- **Density on calc a1-only** (lowerer-emitted `.atm` vs Python source under `cl100k_base`): >2.0× (corpus-dependent — hand-written aspirational form was 3.82× but that wasn't a fair measurement).
- **Round-trip property**: byte-identical on the entire 160-decl `atomadic-forge` corpus. Round-trip caught 4 latent emitter bugs during v1.0.
- **§1 latency benchmark** (with sparse mask, batched timing, all components per the §1 lemma):
  - Mask application p95: 6.0 μs (dev box) / 29.9 μs (Pi 5 projected at 5×)
  - State transition p95: 0.4 μs / 2.2 μs
  - Refinement compiled p95 (AST-walk evaluator): 1.5 μs / 7.7 μs
  - **End-to-end p95: 8.1 μs / 40.7 μs**
  - **Verdict**: PASS the 50μs/token budget with **~1.2× headroom** (not the 30× the v2.0 paper claimed — that was measured on an all-1s mask which made `np.where` a no-op).
- **BPE vocab fill**: 100% (4096/4096) on the 5,138-decl corpus (138 natural Forge + 5000 synthetic).
- **Note**: Pi 5 projections are 5× extrapolation from x86-64 dev hardware. Not measured on actual Pi 5.

## Quick start

```bash
pip install -e ".[dev]"

# Lower a tier-organized Python package
python -m atomadic_lang lower path/to/forge-demo-calc/src/calc -o calc.atm

# Train a BPE on a corpus (multiple packages OK)
python -m atomadic_lang tokenize <pkg1> <pkg2> -o tokenizer.json

# Round-trip verify
python -m atomadic_lang roundtrip calc.atm

# Latency benchmark (corrected v2.6 methodology — all components per §1 lemma)
python -m atomadic_lang benchmark --tokenizer tokenizer.json

# Run all 200+ tests
pytest tests/
```

## Architecture

`.atm` enforces a 5-tier monadic discipline (a0..a4 with upward-only imports). The `atomadic-lang` codebase implementing the lowerer/parser/tokenizer follows the same discipline — and **caught 3 architectural drift bugs at test-collection time over 11 milestones because the import graph rejected them**. The single strongest empirical claim of the project.

```
src/atomadic_lang/
├── a0_qk_constants/   token vocab, grammar states, BPE config, TypedDicts
├── a1_at_functions/   pure helpers: parse, lower, emit, mask eval, AST-walk refinement eval
├── a2_mo_composites/  stateful: BPE trainer, corpus collector
├── a3_og_features/    orchestrators: lower / raise / tokenize / latency / synthetic-corpus
└── a4_sy_orchestration/  Typer CLI (7 subcommands)
```

## Documentation

Read in this order:

1. **[AUDIT.md](docs/AUDIT.md)** — canonical retrospective. Read first if resuming the work.
2. **[PORTFOLIO.md](docs/PORTFOLIO.md)** — how Lang fits the Atomadic ecosystem.
3. **[SWARM_AUDIT.md](docs/SWARM_AUDIT.md)** — 4-critic hostile review and the v2.6 corrections it forced.
4. **[PAPER_v2.md](docs/PAPER_v2.md)** — submission-draft writeup of v0→v2.0 (with v2.6 §7.1 corrections).
5. **[LINEAGE.md](docs/LINEAGE.md)** — append-only milestone log. v0 → v2.6 entries.
6. **[REFINED_DESIGN.md](docs/REFINED_DESIGN.md)** — single coherent design doc post-BEP-6.
7. **[BREAKTHROUGHS.md](docs/BREAKTHROUGHS.md)** — 17 novel claims with cycle-by-cycle audit notes.
8. **[EPIPHANIES.md](docs/EPIPHANIES.md)** — 35+ design/process insights.
9. **[BITDISTILL_PLAN.md](docs/BITDISTILL_PLAN.md)** — execution-ready training recipe (cited arXiv IDs unverified — see AUDIT §4b).
10. **[RELEASE.md](docs/RELEASE.md)** — local release gate plus Forge MCP release checklist.

## What's still pending

- **v3.0**: BitDistill execution from Qwen2.5-Coder-1.5B. The session built the IR; v3.0 introduces it to a fine-tuned model that emits to it.
- **Real Pi 5 hardware deployment** — projections need empirical validation.
- **arXiv citation verification** — 5 IDs in BITDISTILL_PLAN.md still unverified.
- **MultiPL-E-style benchmark shard** — `.atm` translations of HumanEval-164 for cross-language comparison.
- **W-grammar BPE merge filter (B-016)** — implementation queued.
- **PRIZ-as-a1-oracle (B-015)** — implementation queued.

## Status

Pre-alpha but runnable. Source-available under BSL-1.1; converts to Apache-2.0 on 2030-04-27. See [LICENSE](LICENSE).
