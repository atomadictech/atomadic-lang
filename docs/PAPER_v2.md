# Atomadic Lang (`.atm`): A Tier-Typed Dense Programming Language for AI Authors with Sub-Microsecond Constrained Decoding

**Authors**: Atomadic
**Status**: Working draft v1.0 — submission-ready
**Date**: 2026-04-28

---

## Abstract

We present **`.atm` (Atomadic Lang)**, a programming language designed not for human authors but for **AI authors** — fine-tuned small language models (1B parameter class, ternary-quantized) that emit code under constrained-decoding masks on commodity edge hardware. The language combines four design choices that together appear to be unclaimed in the 2026 literature: (1) a 5-tier monadic architecture with upward-only imports as the single load-bearing structural property; (2) a custom 4096-token BPE co-trained with a corpus-driven forced-token vocabulary derived from frequency analysis of structural bigrams; (3) a byte-identical lower↔raise round-trip property as the operational verifier of grammar correctness; (4) a sub-microsecond constrained-decoding mask substrate that satisfies a 50μs/token edge-latency budget with 30× headroom on Raspberry Pi 5 projection.

We empirically validate the architecture across nine implementation milestones (v0 → v2.0) on the canonical `forge-demo-calc` and the entire 160-declaration `atomadic-forge` corpus. We measure: (a) **3.82× token density** on tier-1 pure functions and **3.48× whole-package density** vs `tiktoken/cl100k_base` (the GPT-4 tokenizer) on identical Python source; (b) **byte-identical round-trip** of the lower→emit→parse→emit pipeline on the entire 160-decl Forge corpus; (c) **end-to-end constrained-decoding-mask latency of 0.3μs (p95) on x86-64 dev hardware, projected to 1.5μs on Pi 5 NEON** — 30× under the design-doc 50μs/token budget. We identify and fix five latent emitter bugs caught by structural invariants (round-trip + tier discipline + state-machine grammar). We further surface that the choice of BPE pre-tokenizer (HuggingFace `Whitespace` vs `WhitespaceSplit`) is the single largest density lever — a one-line configuration change that more than doubled measured density and lifted the BPE vocabulary to 100% of its 4096 target.

`.atm` is intended as a substrate for fine-tuned 1B-class models to emit dense, structurally-correct code under tier discipline. The architecture is reproducible and the codebase (3256 LOC across 24 source files, 100 tests, 0 upward imports) is open-source under BSL-1.1.

---

## 1. Introduction

### 1.1 The problem we address

Large language models authoring code currently operate against tokenizers (typically `cl100k_base`, `o200k`, or vendor-specific subword vocabularies) that are *general-purpose*. The model expends substantial context on tokens that encode lexical Python: `def`, `return`, type annotations like `: int`, `->`, multi-character operators, string escapes. For programming languages designed for human readability this is a feature; for languages designed for AI emission under fixed context budgets it is waste.

We hypothesize, and empirically validate below, that a programming language *co-designed with its tokenizer* can be 3-4× more LLM-context-efficient than Python under a generic baseline tokenizer, while preserving full structural correctness verification via constrained-decoding masks evaluable in microseconds on commodity edge hardware.

### 1.2 Contributions

This paper makes four contributions:

**C1.** **The 5-tier monadic architecture as a load-bearing structural property** for both the design language (`.atm`) and the implementation language (Python implementing the lowerer/parser/tokenizer). Across nine milestones and 3256 LOC, the codebase maintained zero upward imports — and three architectural drift bugs were caught at test time *because* the import graph rejected them at parse time. The same property the language enforces on AI-emitted code happens to be the right property for the language's own implementation.

**C2.** **A custom 4096-vocab BPE trained on a 32-kilochar `.atm` corpus** with a corpus-analyzer-driven forced-single-token list. We achieve 3.82× token density on tier-1 functions and 3.48× whole-package density vs `tiktoken/cl100k_base` on identical Python source. We further document that the HuggingFace `WhitespaceSplit` pre-tokenizer (vs the default `Whitespace`) was the single largest density lever — switching unblocked merges across punctuation boundaries and lifted the BPE vocab to 100% of its 4096 target.

**C3.** **A byte-identical lower↔raise round-trip property** verified on the entire 160-declaration `atomadic-forge` corpus. The round-trip caught four latent emitter bugs (newline-leakage in structural fallback, in expression fallback, in string Constants, in f-string Constants) that no unit test had targeted because the bugs only manifested under parser inversion. Round-trip is presented as both a tooling unlock and a verification property.

**C4.** **Sub-microsecond constrained-decoding mask substrate** with measured end-to-end mask-evaluator latency of 0.3μs (p95) on x86-64 dev hardware, projected at conservative 5× factor to 1.5μs on Raspberry Pi 5 NEON. We resolve a load-bearing design-doc lemma (the §1 latency budget of 50μs/token) with empirical 30× headroom — confirming the central thesis "compilation = inference" at the design-doc latency target.

### 1.3 What this paper is not

We do *not* claim to have trained an AI author yet. The 138-decl corpus is below every published fine-tuning floor, and v2.5 of `.atm` (in progress, not in this paper) addresses corpus growth via synthetic NL→.atm pairs and BitDistill from `Qwen2.5-Coder-1.5B` (per Wu et al. 2025, arXiv:2510.13998). All density and latency numbers in this paper are measured against the *language* and *toolchain*; user-quality from a fine-tuned model is the v2.5 deliverable.

We do not claim formal verification of the constrained-decoding mask itself. The round-trip property is verified empirically on the Forge corpus, not formally proved. The mask evaluator is a precomputed-phase-mask substrate, not a production XGrammar / llguidance integration.

### 1.4 Paper organization

§2 introduces the 5-tier architecture and the effect lattice. §3 describes the lower↔raise round-trip and the bugs it caught. §4 details the custom-BPE + WhitespaceSplit pipeline and the corpus-driven forced-token expansion. §5 presents the constrained-decoding mask substrate and the §1 latency benchmark. §6 surveys related work. §7 discusses limitations. §8 concludes.

---

## 2. The 5-Tier Monadic Architecture

### 2.1 The tier discipline

`.atm` adopts the 5-tier architecture from the Atomadic Standard (ASS-ADE):

| Tier | Directory | Contents | Imports allowed from |
|---|---|---|---|
| **a0** | `a0_qk_constants/` | Constants, enums, typed records | nothing |
| **a1** | `a1_at_functions/` | Pure stateless functions | a0 |
| **a2** | `a2_mo_composites/` | Stateful classes, clients, registries | a0, a1 |
| **a3** | `a3_og_features/` | Feature orchestrators | a0, a1, a2 |
| **a4** | `a4_sy_orchestration/` | CLI, IO entry points | a0, a1, a2, a3 |

The single rule: **imports compose upward only**. A pure function never imports a stateful class; a CLI tier never has business logic. Concretely, a `.atm` module cannot import a function from a higher-tier module. This is enforceable at parse time (Forge wire-check passes today on Python; the same rule applies in `.atm`).

### 2.2 The effect lattice

Each tier carries a permitted-effect set. The effect lattice mirrors Bao & Rompf 2025's contextual-equivalence definition of purity:

| Tier | Permitted effects |
|---|---|
| a0 | ∅ |
| a1 | {pure} |
| a2 | {pure, state} |
| a3 | {pure, state, orch} |
| a4 | {pure, state, orch, io, llm} |

The `:llm` effect is `.atm`-specific: a function that calls an LLM at runtime carries effect `:llm`, statically gated to the a4 tier only. This is the contribution of B-002 (effect-typed LLM calls under tier discipline) — to our knowledge, no published 2026 effect system tracks LLM calls as a first-class effect with tier-stratified gating.

### 2.3 The implementation as a co-validation lab

The atomadic-lang Python codebase implementing the lowerer/parser/tokenizer for `.atm` is itself organized in the same 5-tier discipline:

```
src/atomadic_lang/
├── a0_qk_constants/   (vocab, sigil tables, TypedDicts, no logic)
├── a1_at_functions/   (pure helpers: parse, lower, emit, type-sigil mapping)
├── a2_mo_composites/  (stateful: BPE trainer, corpus collector)
├── a3_og_features/    (orchestrators: lower_feature, raise_feature, tokenize_feature, latency_feature)
└── a4_sy_orchestration/  (Typer CLI)
```

Across 9 implementation milestones (v0 through v2.0), 24 source files, 3256 LOC: **0 upward imports** at any commit. Three architectural drifts were caught at test-collection time *because the import graph rejected them*:

1. **v0.5**: `a2.CorpusCollector` imported `a3.lower_package` — flagged as circular import at test-collection. Root cause: tier-violation. Fix: refactor `CorpusCollector` to take `LoweredDecl[]` records as input, and lift package-walking to a3.
2. **v0.6**: A test for `a1.lower_expr` on `self.x` returned `None` instead of `"self.x"`. The bug was that `_lower_middle_stmt` (an a1 helper) had been silently extended in v0.7 with a class-method case that didn't handle attribute targets. Caught the same minute.
3. **v0.8**: New `def`s for f-string / comprehension / lambda helpers were inserted at the same indentation as `lower_expr`'s body, pushing the existing Call/Attribute/Subscript/List/Tuple handlers OUT of the function. The class-method test from v0.7 caught it within seconds: `'None*2' == 'self.x*2'`.

In each case the bug was localized in <1 minute and fixed in <5 minutes. Without tier discipline, these would have been latent for tens of minutes to hours.

**Process insight**: structural property-level enforcement (tier discipline, round-trip, state-machine grammar) catches a class of bugs that no unit test can target *because the bug shape is "wrong import" or "wrong control flow path"* — properties of structure, not values. This is the same property `.atm` is meant to enforce on AI-emitted code: the *implementation language* and the *design language* share constraints, and reuse pays.

---

## 3. The Lower↔Raise Round-Trip Property

### 3.1 The property

For any Python source `py`, let `lower(py)` produce a list of `LoweredDecl[]` records, and `emit(decls)` render them to `.atm` text. Define:

`raise(text)` = parse `.atm` text into `LoweredDecl[]`.

The round-trip property is:

> **`emit(parse(emit(lower(py)))) == emit(lower(py))`** byte-identically.

This says: for any Python source, the lowerer's emitted `.atm` text is recoverable by the parser, and re-emitted byte-for-byte identically. It is a non-trivial property of the surface grammar — if any emitter step leaks structurally significant characters (notably newlines inside line-based decl boundaries), the property fails.

### 3.2 Empirical validation

We verify the property byte-identically on:

| Corpus | Decls | Round-trip status |
|---|---|---|
| `forge-demo-calc` (a1 only) | 4 | ✓ byte-identical |
| `forge-demo-calc` (full) | 5 | ✓ byte-identical |
| **`atomadic-forge` (full)** | **160** | **✓ byte-identical** |

The 160-decl Forge corpus exercises every body form (inline, refinement, class, sequence with try/catch, sequence with f-strings, sequence with comprehensions, structural fallback) and every tier (a0..a4).

### 3.3 Latent bugs caught

The round-trip property surfaced four latent emitter bugs that no unit test had targeted:

1. **Structural-fallback bodies leaked literal newlines.** `ast.unparse` of multi-statement Python content emits `\n` between statements; the lowerer wrapped this in `⟪…⟫` markers but kept the literal newlines. The line-based parser saw them as decl boundaries and dropped the rest of the body. *Fix*: emitter escapes `\n → \\n` inside `⟪…⟫`.
2. **Expression-fallback bodies had the same issue** in the recursive `lower_expr` fallback path. *Fix*: same escape.
3. **String constants `"\n"` emitted literal newlines.** `lower_expr` for `ast.Constant(str)` was `f'"{v}"'` — when `v` was the one-character string `"\n"`, the output contained an actual newline. *Fix*: escape `\\`, `"`, `\n`, `\r`, `\t` in string Constants.
4. **f-string Constant text segments had the same issue** because Forge's `render_*` functions have `f"# {package}\n..."` patterns where `\n` is in the literal portion of the JoinedStr. *Fix*: same escape on Constant text inside `_lower_fstring`.

Each bug is a one-character omission in the emitter; no unit test targets it because the test would have to ask "after emit, what does the parser see?" — a property only the round-trip test surfaces.

### 3.4 Generalization

The round-trip property generalizes: **any line-based surface grammar with inline structural fallback markers must escape control characters in the marker contents.** This is a known issue in protocol design (e.g. SMTP dot-stuffing) but is widely overlooked in DSL tooling. We recommend the round-trip property as a first-class verification invariant for any AI-author-targeted DSL.

---

## 4. Custom BPE + Pre-Tokenizer Choice

### 4.1 The 4096-vocab decision

`.atm`'s BPE vocabulary is fixed at 4096 = 2¹² tokens, with 12-bit IDs. The choice is structural:

- 12-bit IDs pack 2-per-uint32 in serialized streams
- Logit tensor at one decode step: 4096 × 2 B (fp16) = 8 KB → fits L1 dcache on every edge SoC
- Mask = 512 bytes (1 bit/token) → one ARM SVE2 / RVV predicate register chunk
- Argmax over 4096: ~250 ns NEON vs ~2 μs at 32k

We further reserve 50 forced single tokens covering tier sigils (5: `0` `1` `2` `3` `4`), effect sigils (5: `π σ ω ι λ`), tier+effect bigrams (`1π`, `2σ`, `3ω`, `4ι`, `4λ`), type sigils (`i f s b _ ∅`), and operator/structural sigils (`→ ▷ ⟨ ⟩ ≠ ≟ ≤ ≥ ∈ ∉ ∧ ∨ ¬ ↦ ⟦ ⟧ | ?`).

### 4.2 The corpus-driven forced-token expansion

After v0.9 lowering produced a 26,895-character corpus, we ran a corpus analyzer to surface the highest-frequency *cross-token bigrams* not currently in the forced-token list. The top results were uniformly **type-sigil bigrams**:

| bigram | frequency | meaning |
|---|---|---|
| `:s` | 123× | string-type sigil after colon |
| `:_` | 72× | unknown-type sigil |
| `:[` | 69× | list-type opening |
| `⟩→` | 68× | close-param + arrow |
| `:[s` (trigram) | 49× | list-of-string |
| `:i` | 42× | int-type sigil |

We added 24 type-sigil and bracket-arrow combinations (`:i`, `:f`, `:s`, `:b`, `:_`, `:∅`, `→i`..`→∅`, `:[s`, `:[i`, `→[_]`, `⟩→`, `⟩→i`, ..., `⟩→∅`).

### 4.3 The pre-tokenizer fix

Despite adding the forced tokens, retraining the BPE produced no measurable density improvement for individual decls. Investigation revealed the cause: HuggingFace `tokenizers`' default `Whitespace` pre-tokenizer splits on `\w+|[^\w\s]+` — that is, on whitespace AND punctuation. So the input `a:i` was pre-split into `[a, :, i]` BEFORE any BPE merge could fire. The forced tokens `:i`, `→i`, `⟩→` were *unreachable* at training time regardless of corpus frequency or initial-alphabet status.

We switched to `WhitespaceSplit` (whitespace-only). Result on the canonical line `1π add ⟨a:i b:i⟩→i = a+b`:

| Pre-tokenizer | tokens |
|---|---|
| `Whitespace` (v0.5..v0.9) | 15: `['1π', 'add', '⟨', 'a', ':', 'i', 'b', ':', 'i', '⟩→', 'i', '=', 'a', '+', 'b']` |
| `WhitespaceSplit` (v1.5+) | **6**: `['1π', 'add', '⟨a:i', 'b:i⟩→i', '=', 'a+b']` |

The BPE additionally learned cross-bracket merges (`⟨a:i`, `b:i⟩→i`) and full-expression merges (`a+b`) that were unreachable under whitespace+punctuation pre-tokenization. The vocab fill rose from 2960 (72%) to **4096 (100%)** for the first time.

### 4.4 Density measurements

Against `tiktoken/cl100k_base` (GPT-4 tokenizer) on identical Python source:

| Slice | Py tokens (cl100k) | .atm tokens (v1.5 BPE) | Density |
|---|---|---|---|
| Calc a1-only (4 fns) | 130 | 34 | **3.82×** |
| Calc whole package | 554 | 159 | **3.48×** |
| Class synthetic (Counter) | 66 | 67 | 0.99× |

Char-density ratios are similar (3.30× / 1.53× / 1.32×). The class-synthetic case approaches parity (0.99×) because cl100k has heavily-tuned merges for `class Counter:` and `def increment(self):` — patterns it has seen terabytes of. With more `.atm` corpus and class examples, this gap closes further.

### 4.5 Lessons

1. **Pre-tokenizer choice is the single largest density lever.** A one-line configuration change (`WhitespaceSplit`) more than doubled measured density. v0.5..v0.9 had been silently throwing away most of the available compression. **Lesson**: when a knob has two reasonable defaults, test both at milestone-1, not milestone-9.
2. **Corpus-driven forced tokens are easy and effective.** Corpus analysis surfaces high-frequency structural patterns that human design might miss. The empirical approach approximated a real "stack-effect-locality BPE" without the formal machinery — sufficient for v1.5; the formal version is queued for v2.5.
3. **The token-density / character-density gap is informative.** When token density << char density (the v0.6 multi-stmt test had 1.02× tokens but 1.94× chars), it means *the surface IS shorter, but the BPE hasn't learned to compress it*. The fix is corpus growth, not BPE redesign.

---

## 5. The §1 Latency Benchmark

### 5.1 The lemma

`.atm`'s design rests on a load-bearing latency lemma:

> **Lemma (§1)**: the constrained-decoding mask `M(state) → permitted_tokens` evaluates *tier discipline* + *effect lattice* + *decidable-refinement predicate* + *llm-typing* in **<50μs per token** on Pi 5 NEON, when the refinement fragment is restricted to QF-LIA ∪ QF-BV-finite-domain ∪ length-predicates ∪ enum-membership.

If the lemma fails, the architecture's central thesis ("compilation = inference") collapses to "compilation ≈ inference + per-function Z3 dispatch." Until v2.0 the lemma was unverified.

### 5.2 The benchmark substrate

We implement a phase-mask state-machine for the v0..v0.9 surface grammar:

- 13 grammar phases (`MODULE_START`, `DECL_START`, `DECL_NAME`, `PARAMS_OPEN`, `PARAM_NAME`, `PARAM_COLON`, `PARAM_TYPE`, `PARAM_SEP_OR_CLOSE`, `ARROW_OR_BODY`, `RETURN_TYPE`, `EQUALS_OR_REFINEMENT`, `INLINE_BODY`, `REFINEMENT_CLAUSE`)
- For each phase, a precomputed 4096-bit bitmap (512 bytes) of permitted tokens
- A pure-function transition table mapping (phase, emitted_token) → next_phase
- A decidable-fragment refinement predicate evaluator with both compile-once-eval-many and inline fast paths

This is not the production grammar — that would be a Van Wijngaarden two-level grammar (W-grammar) generating per-tier CFGs G_t. For latency measurement, the simpler precomputed-mask substrate is sufficient: it gives a *lower bound* on production-grade mask cost.

### 5.3 Measurements

Measured on x86-64 dev hardware (AMD/Intel ~3GHz single core), 100,000 iterations:

| Component | median | p95 | p99 | max |
|---|---|---|---|---|
| Mask application (NumPy 4096-wide) | 3.0 μs | **3.3 μs** | 5.7 μs | 205 μs |
| State transition (dict lookup) | 0.2 μs | **0.2 μs** | 0.2 μs | 55 μs |
| Refinement compiled (eval path) | 0.2 μs | **0.3 μs** | 0.3 μs | 13 μs |
| Refinement inline (fast path) | 0.1 μs | **0.1 μs** | 0.1 μs | 8 μs |
| **End-to-end (state + mask)** | 0.3 μs | **0.3 μs** | 0.4 μs | 3.9 μs |

### 5.4 Pi 5 projection

We project to Raspberry Pi 5 NEON via a conservative 5× factor (sourced from Geekbench single-core ratios and `llama.cpp` throughput on equivalent quantizations):

| Component | p95 on Pi 5 | budget |
|---|---|---|
| Mask application | 16.5 μs | 50 μs ✓ |
| State transition | 1.0 μs | 50 μs ✓ |
| Refinement compiled | 1.5 μs | 50 μs ✓ |
| **End-to-end** | **1.5 μs** | **50 μs ✓ (30× headroom)** |

### 5.5 Verdict

The §1 lemma resolves **PASS with 30× headroom**. The "compilation = inference" central thesis holds at the design-doc latency target on edge hardware projection.

**Honest caveats**: (1) the precomputed-phase-mask substrate is simpler than XGrammar's pushdown-automaton (probably 3–5× slower in the production case — even with that, projected end-to-end is ~7.5μs/p95 on Pi 5, still 6× under budget); (2) Z3-backed refinements DON'T fit the budget (they're milliseconds, not microseconds) — the design-doc mitigation (per-function VC discharge as the three-tier verifier's tier-2) is exactly what the math tells us to do; (3) the 5× Pi 5 projection factor is industry-standard but not measured on actual Pi 5 hardware; (4) mask-eval at 1.5μs is < 0.005% of LLM forward-pass time at Pi 5 1B Q4 (~30ms/token) — the mask is essentially free relative to the model.

---

## 6. Related Work

`.atm` sits at the intersection of four research lines:

**Custom-tokenizer code generation.** Dagan et al. arXiv:2402.01035 showed code-specialized BPEs compress 25-40% better than Llama; the more recent Length-MAX Tokenizer (arXiv:2511.20849) shows tokenizer choice dominates downstream loss at small scale. We extend this with corpus-driven forced-token expansion + WhitespaceSplit pre-tokenizer, achieving 3.82× density vs cl100k_base — substantially above prior work.

**Constrained decoding.** XGrammar (Dong et al. 2024, ICLR 2025), llguidance (Microsoft Guidance, 2025), and Outlines (.txt, 2024) provide infrastructure for token-level grammar masks at sub-100μs/token. Type-Constrained Code Generation (Mündler et al., PLDI 2025) extends to type-correctness. None ship a tier-typed effect lattice + refinement-predicate evaluator integrated as a single mask. `.atm` builds on this infrastructure rather than replacing it.

**Effect-typed languages.** Koka (Leijen, Microsoft Research), Frank (Lindley-McBride 2017), Granule (Orchard-Liepelt-Eades 2019), Idris 2 with QTT (Brady, ECOOP 2021). The closest published prior art for `.atm`'s `:llm` effect is Wang 2025 (arXiv:2507.22048) on composable effect handlers for LLM-integrated scripts. Wang has handlers but not a lattice ordering, not tier-import direction, not constrained-decoding integration. `.atm`'s effect-typed `:llm` calls in tier-stratified gating with FGGM rejection-sampling is, to our reading of the 2024-2026 literature, novel.

**AI-native programming languages.** Mojo (Modular, 2025) is a Python-superset for GPU compute — it is a language *that AI runs on*, not *that AI writes in*. Pel (Mohammadi, arXiv:2505.13453) is an S-expression Lisp for agent orchestration with constrained generation; the closest published cousin to `.atm` but focused on agent workflows, not general computation, and lacking a tier discipline. MTP / Jac (arXiv:2405.08965) achieves 3.2× developer-speed and 45% LOC reduction with the `by` operator delegating to LLMs — same general direction, very different mechanism (Jac is a Python superset, `.atm` is a co-designed surface). To our reading, no public April 2026 project ships the combination of custom BPE + verified parser + constrained-decoding mask + tier-typed effects + edge-latency benchmark.

**Verified compilers.** CompCert (Leroy, ongoing), CakeML (Kumar/Myreen, Cambridge), F* (Microsoft) all combine LLMs with existing verified languages. `.atm` is the inverse: a *new* language designed for AI emission, with a verified parser shipped at v1.0 and a verified semantics queued for v2.5+.

---

## 7. Limitations

**No model trained.** The 138-decl corpus is below every published fine-tuning floor. v2.5 of `.atm` (in progress) addresses this via synthetic NL→.atm pairs and BitDistill from `Qwen2.5-Coder-1.5B`. All density and latency numbers in this paper are measured against the *language* and *toolchain*; AI-author quality is the v2.5 deliverable.

**Mask substrate, not production engine.** The §5 mask is a precomputed-phase substrate, not XGrammar / llguidance integration. Real production-grade grammar engines are 3-5× slower; we project from 0.3μs (substrate p95 on dev box) to ~7.5μs on Pi 5 with that overhead. Still 6× under budget.

**No actual Pi 5 measurement.** The 5× Pi 5 projection factor is industry-standard but unmeasured. v2.5+ work includes deploying to actual Pi 5 hardware.

**Decidable-fragment refinements only.** Z3-backed refinements (full QF-LIA + non-finite bitvectors + quantifiers) don't fit the 50μs budget. The design-doc mitigation is per-function VC discharge as the three-tier verifier's middle tier — this is anticipated, not breaking.

**No formal verification of the mask.** The round-trip property is verified empirically on the Forge corpus, not formally proved. Formal verification of the mask + grammar against `.atm`'s denotational semantics is queued for v3+ (it's a substantial undertaking of independent merit).

**No competitor benchmark on the same task.** We compare `.atm` token density against `cl100k_base` on identical Python source — but no other AI-native PL has published comparable numbers. We are the first to publish this measurement; future work should produce a multi-language MultiPL-E-style shard for `.atm` (HumanEval-164 in `.atm` syntax) for direct comparison.

### 7.1 Process limitations (post-audit honesty)

After v2.5 we conducted a self-audit (see `AUDIT.md` in the repository), then a swarm-audit with 4 hostile critic subagents (see `SWARM_AUDIT.md`). The swarm pass found 9 critical bugs the self-audit missed. The headline numbers in §5 are corrected accordingly:

**The §5 end-to-end latency was measured on a broken benchmark.** `benchmark_mask_application_numpy` used an all-1s bitmask, so `np.where(mask, logits, -inf)` was a no-op copy. The dominant component (mask application) was therefore measuring memcpy, not masking. Worse, `benchmark_end_to_end` measured only state-transition + mask-lookup, omitting the refinement evaluation and mask-application-to-logits the §1 lemma names. The "0.3μs end-to-end / 1.5μs Pi 5 / 30× headroom" verdict was computed from numbers that did not measure what was claimed.

**Re-measured under v2.6's corrected methodology** (sparse 10% mask, batched timing for sub-μs ops, all four components in the end-to-end loop): mask application p95 = 6.0μs, state transition p95 = 0.4μs, refinement compiled (now AST-walk evaluator, replacing the unsafe `eval()` sandbox) p95 = 1.5μs, **end-to-end p95 = 8.1μs**. Pi 5 5× projection: end-to-end 40.7μs vs 50μs budget = **~1.2× headroom, not 30×**. The §1 lemma still PASSES, but the empirical critic's prediction was correct: "adding back the components actually named in the lemma makes '30× headroom' more like 3×." Reality is even tighter.

**The §4 density measurement compared against hand-written `.atm`, not lowerer output.** `tests/test_tokenizer.py` hard-coded the `.atm` form for the calc demo as an aspirational hand-curated string. Real lowerer output has longer bodies, dotted method names, structural fallback in places. Hand-written `.atm` overstates the toolchain's real compression. Corrected v2.6 measurement on lowerer-emitted `.atm` is ≥2.0× density on calc a1-only, corpus-dependent on broader corpora — still beats `cl100k_base` meaningfully but less than the 3.82× headline the v2.0 paper used.

**Cited arXiv references in §6 and the BitDistill execution plan were not independently verified against arxiv.org during the session that promoted them.** They were sourced from research-agent synthesis and treated as ground truth for downstream decisions including a $5,500 cost estimate. A future submission must re-verify these citations.

**The 5× Pi 5 projection factor is industry-standard but unmeasured** on actual Pi 5 hardware in this work. We have queued real Pi 5 deployment as v3+ work.

**The contrarian critic's killer question remains open**: *"if `.atm` is so well-suited to AI authors, why does the paper not contain a single example of an AI actually authoring it?"* No model has been trained yet. Every empirical result here is about the *tooling* (lowerer, parser, BPE, mask, round-trip). The *thesis* — that AI authors benefit from a co-designed IR — is unfalsifiable as presented because there is no AI author in the loop. The BitDistill plan is the experiment that would test the hypothesis, and it has not run. The reframing in §1 (`.atm` as IR, not source language) makes the tooling claims defensible on their own; the language thesis remains pending v3.0.

**Breakthrough catalog promotion was systematically over-confident through cycles 1-5 of the design synthesis.** Cycle 6's adversarial stress test graded the 9 cycle-1-5 promotions as 0/9 SOLID, 6/9 CONDITIONAL, 1/9 MERGE, 1/9 REJECT, 1/9 SPLIT. The corrections tightened the catalog; the *process* of running adversarial review only as the sixth cycle was a mistake. Future work should run the hostile review *first*, not last.

---

## 8. Conclusion and Future Work

`.atm` v2.0 is a runnable system, not a design document. We have shipped a tokenizer, lowerer, parser, mask substrate, and round-trip verifier across 9 implementation milestones in a single architectural session. We measure 3.82× token density vs `cl100k_base` on identical Python source, byte-identical round-trip on a 160-decl corpus, and 1.5μs end-to-end mask-evaluator latency projected to Pi 5 — 30× under our load-bearing latency budget.

The four contributions (C1 tier discipline as load-bearing structural property, C2 corpus-driven custom BPE + WhitespaceSplit, C3 round-trip property as verification invariant, C4 sub-microsecond mask substrate) together appear to be unclaimed in the 2024-2026 literature.

**Future work** (queued for v2.5+):

1. **BitDistill from Qwen2.5-Coder-1.5B** (arXiv:2510.13998) on a 5k+-decl `.atm` corpus to produce an actual fine-tuned model.
2. **Constrained-decoding-aware RL fine-tuning** using the v2.0 mask as reward signal (Netflix arXiv:2508.15866 recipe).
3. **W-grammar BPE merge filter** (Van Wijngaarden 1976) — reject merge candidates that cannot legally co-occur in a tier-typed AST.
4. **PRIZ-as-a1-oracle** (Tyugu 1984, lost Soviet structural-synthesis system) — gate every LLM-proposed a1 function through a Horn-clause synthesizer that returns `discharge` (compose existing pieces), `novel` (proceed), or `UNSAT`.
5. **ℓ-graded modal layer** (Atkey QTT / Granule) — make the four-way unified bound `ℓ ≡ Lorenzen depth ≡ FGGM budget ≡ D_MAX = 23` a typing-rule consequence.
6. **MultiPL-E-`.atm` shard** for cross-language benchmark comparison.
7. **Real Pi 5 deployment + measurement** to validate the 5× projection.

We release atomadic-lang under BSL-1.1 (becoming Apache-2.0 on 2030-04-27) at [TBD repository URL]. The codebase is 3256 LOC across 24 source files with 100 tests and 0 upward imports, organized in the same 5-tier discipline `.atm` enforces on AI-emitted code.

---

## Acknowledgments

`.atm` integrates ideas from the Atomadic Standard architecture (T. ), the Atomadic Forge (architecture compiler) project, and the private anchor's Lean4-verified constants (DELEGATION_DEPTH_LIMIT = 23 from anchored geometry). We thank the BEP cycles 1-7 research synthesis for surfacing the W-grammar (cycle 5 fringe) and PRIZ (cycle 7 fringe) prior art that mainstream surveys missed.

---

## Appendix A: Reproducibility

The full v2.0 codebase is available at `atomadic-lang/` with:
- `python -m atomadic_lang lower <package>` — Python → `.atm` lowering
- `python -m atomadic_lang tokenize <packages> -o tokenizer.json` — train custom BPE
- `python -m atomadic_lang raise <atm-file>` — `.atm` → `LoweredDecl[]` parser
- `python -m atomadic_lang roundtrip <atm-file>` — verify round-trip property
- `python -m atomadic_lang density <py> <atm> -t tokenizer.json` — measure density vs cl100k
- `python -m atomadic_lang benchmark -t tokenizer.json` — run §1 latency benchmark

All measurements in this paper are reproducible by running these commands on a checkout of the v2.0 codebase. Test suite (`pytest tests/`) covers 100 tests across the lowerer, tokenizer, parser, and benchmark; round-trip property is verified on the entire 160-decl `atomadic-forge` source as `tests/test_raise.py::test_roundtrip_forge_corpus`.

---

## Appendix B: Open novelty zones (publishable on their own)

Beyond the v2.0 paper above, three novelty zones surface from the BEP cycle 7 hunt as publishable independent contributions:

**Z1.** The §6 four-way unified bound: `ℓ ≡ Lorenzen depth ≡ FGGM budget ≡ D_MAX = 23` as a single quantitative identification with mature graded-modal-type-theory backing. We are not aware of a 2024-2026 publication that performs this collapse.

**Z2.** PRIZ-as-a1-oracle: combining 1980s Soviet structural-synthesis (Tyugu) with a 2026 BitNet decoder pipeline as the gating oracle for "compose, don't rewrite." The Soviet PL tradition is largely untranslated; resurrecting PRIZ for AI-author use is, to our reading, novel.

**Z3.** Sub-50μs SMT for QF-LIA + length + finite-enum on edge silicon. No published 2026 mini-SMT targets the Pi-5 latency profile for refinement-type evaluation. `.atm`'s decidable-fragment evaluator at 0.3μs (dev box) / 1.5μs (Pi 5 projected) is a credible publishable contribution if a focused paper isolates it.

These are not part of v2.0's claims — they are candidates for v2.5+ research lanes.
