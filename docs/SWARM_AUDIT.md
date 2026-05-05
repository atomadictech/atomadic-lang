# Swarm Audit (post-v2.5)

**Date**: 2026-04-28
**Method**: 4 hostile critic subagents in parallel — code/engineering, architecture/design, empirical-claims, strongest-case-against contrarian.
**Outcome**: 9 critical fixes (committed as v2.6) + reframing of `.atm` from "AI-author programming language" to "verified IR for AI-emitted code."

This document records what the swarm found that the prior self-audit missed, and what was actually fixed.

---

## What the prior self-audit caught

The self-audit before this swarm pass identified four process-level changes:
1. Pre-tokenizer config bug deferred 4 milestones
2. Round-trip property deferred to v1.0 instead of v0.5
3. Breakthroughs promoted without hostile pass
4. Milestone granularity 2-3× too fine

It also flagged honest gaps: Pi 5 projections vs measurements, unverified arXiv citations, no E2E tests, doc/code ratio.

What it **missed**: the load-bearing empirical claims of the v2.0 paper were measured on broken benchmark code.

---

## What the swarm caught that the self-audit didn't

### 1. The §1 latency benchmark was measuring nothing for its dominant component

`benchmark_mask_application_numpy` built an all-1s mask (`b"\xff" * MASK_BYTES`), so `np.where(bool_mask, logits, -inf)` was a no-op copy. The reported 3.3μs p95 mask number measured **memcpy speed**, not actual masking. Since mask application is the dominant component, the entire v2.0 §1 verdict (1.5μs Pi 5 projection, 30× headroom) was computed on a meaningless number. **Fixed in v2.6**: sparse 10% mask + batched timing.

### 2. The end-to-end benchmark didn't include the components named in the §1 lemma

`benchmark_end_to_end` measured only state transition + phase mask lookup. It did **not** include: refinement evaluation, mask application to logits, or LLM-typing. The §1 lemma defines `M(state)` as all four. The "0.3μs end-to-end" was the cost of two of four components, not the lemma's full cost. **Fixed in v2.6**: full per-token path including all four components, batched.

### 3. Sub-microsecond benchmarks were measuring timer noise

`time.perf_counter_ns()` has ~100ns Windows resolution; per-op timing of sub-microsecond ops is dominated by the timer call itself. Reported "0.2μs median" was effectively the timer floor. **Fixed in v2.6**: batched timing — measure 1000 ops, divide.

### 4. The density measurement compared cl100k vs hand-written `.atm`, not lowerer output

`tests/test_tokenizer.py:188-194` hard-coded the `.atm` form for the calc demo as a literal string. The real lowerer produces longer bodies, dotted method names, structural fallback, etc. Hand-written `.atm` over-states what the toolchain actually produces. **Fixed in v2.6**: density tests now use `emit_module(*lower_file(...))` to measure real lowerer output, not aspirational hand-curated text. The `>= 0.5` density assertion (which passes when `.atm` is *worse* than Python) was tightened to `>= 1.0`. The headline `>= 2.0` test is now against real lowerer output.

### 5. The refinement evaluator's `eval()` sandbox was trivially exploitable

`compile_predicate` filtered `__`, `;`, and `import` from the source string but used Python `eval()` for execution. Strings like `x.upper()` or `x.pop()` passed the filter and called arbitrary attributes on bound objects. **Fixed in v2.6**: replaced with an AST-walk evaluator that only handles a whitelist (BinOp, Compare, BoolOp, Call to whitelisted functions). The new evaluator is ~5× slower than `eval()` (1.5μs vs 0.3μs p95) — security cost, paid once per predicate.

### 6. `_negate_expr` corrupted refinement guards with `or`/`and`

For `if a == 0 or b == 0: raise ValueError(...)`, the negated guard fell through to `¬a≟0∨b≟0` — wrong precedence, silent corruption. The `pre` clause of every multi-condition refinement was wrong since v0. **Fixed in v2.6**: applied De Morgan recursively + parenthesised fallback.

### 7. `type_to_sigil` mis-lowered tuple/Mapping/Iterable to `[_]`

`tuple[int,str]`, `Mapping[K,V]`, `Iterable[T]` all lowered to `[_]` because the recursive call returned `_` for unknown bases, and `_` was in the list-condition match. Every tuple-typed return in the corpus was mis-tagged. **Fixed in v2.6**: dispatch on the actual base name (`node.value.id`), with explicit cases for tuple → `(A,B,C)`, Mapping → `{K:V}`, Optional → `?T`, Union → `?T₁`, Set → `{T}`, list → `[T]`.

### 8. The `_synth_refinement` synthetic generator produced unparseable `.atm`

The hand-coded `atm_line = f"1π {name} ⟨...⟩→f ; pre {pre} ; body {body}"` did not match the multi-line form `emit_decl` produces for `body_form="refinement"`. Synthetic training corpus contained an `.atm` shape the parser could not round-trip — poisoning the corpus. **Fixed in v2.6**: synthetic generator now uses `emit_decl(decl)` to produce the canonical form.

### 9. The `INLINE_BODY` exit transition was unreachable

The state machine checked `token == "\n"` to exit `INLINE_BODY`, but `WhitespaceSplit` pre-tokenizer never emits a bare newline as a BPE token. The state was permanently stuck. The hardcoded `"⟨a"` substring check for params named `a` had a similar narrow-scoped bug. **Fixed in v2.6**: detect end-of-decl by tokens containing newlines OR starting with a tier digit.

---

## The honest re-measurement (v2.6)

After fixing the methodology, the v2.0 latency claims look very different:

| Component | v2.0 reported (rigged) | **v2.6 honest** | Pi 5 projection (5×) |
|---|---|---|---|
| Mask application p95 | 3.3 μs | **6.0 μs** | 29.9 μs |
| State transition p95 | 0.2 μs | **0.4 μs** | 2.2 μs |
| Refinement compiled p95 | 0.3 μs | **1.5 μs** | 7.7 μs |
| Refinement inline p95 | 0.1 μs | 0.2 μs | 1.0 μs |
| **End-to-end p95** | **0.3 μs** | **8.1 μs** | **40.7 μs** |

**The §1 lemma still PASSES** (40.7μs Pi 5 projected vs 50μs budget) but with **~1.2× headroom, not 30×**. The empirical critic predicted this exactly: "adding back the components actually named in the lemma makes '30× headroom' more like 3×." Reality is even tighter — ~1.2×.

This is the kind of margin that should drive design decisions. With 30× headroom we could have added complexity to the mask substrate cheaply; with 1.2× headroom every additional component cost matters and the production path needs care.

---

## The reframing the swarm forced

The architecture critic's deepest cut: **`.atm` should be an IR, not a source language.** Three independent critics converged: humans do read `.atm` (the audit shows we read it, debug it, write tests against it); AI authors do not yet emit it (no model trained); the density/latency claims compare against general-purpose Python tokenizers in ways that only make sense if `.atm` is positioned as IR.

The reframe dissolves several architectural critiques:
- Custom 4096-vocab BPE: appropriate for an IR (binary formats have custom encodings); marginal for a source language (locks in monolingual model).
- Tier sigils eating 2 bits: appropriate for an IR (structured opcodes); wasteful for a source language.
- AI-author-only access: appropriate for an IR (humans never read object files); wrong for a source language.
- Round-trip byte-identity: the natural IR invariant; brittle for a source language.
- Sub-microsecond mask: appropriate for an IR (line-rate processing); irrelevant for source.

**Reframe committed**: README and PAPER §7.1 now lead with "verified IR for AI-emitted code." Every architectural choice now has an aligned justification.

---

## The contrarian's REJECT verdict — what we did with it

The contrarian critic reviewed the work as if writing a hostile paper review and recommended REJECT, not REVISION. The killer question:

> If `.atm` is so well-suited to AI authors, why does the paper not contain a single example of an AI actually authoring it?

This is correct. Every empirical result is about the *tooling* (lowerer, parser, BPE, mask, round-trip). The *thesis* (AI authors benefit from a co-designed IR) is unfalsifiable as presented because there is no AI author in the loop. The BitDistill plan is the experiment that would test the hypothesis, and it has not run.

What we did:
- The reframing acknowledges this — `.atm` is positioned as IR (which is testable on tooling alone) rather than as a programming language for AI authors (which requires the model).
- AUDIT §4b already flagged unverified arXiv citations; this swarm audit elevates that flag.
- BitDistill execution remains queued; the paper now explicitly distinguishes "the IR works" (provable now) from "AI authors benefit from emitting to it" (provable only after model training).

What we explicitly did NOT do:
- Run BitDistill. That's a $5,500 / 10-day GPU job; out of scope for this audit pass.
- Re-author the paper from scratch. Updates landed in §7.1 limitations.
- Drop the breakthrough catalog. Claims survive after cycle-6 + cycle-7 corrections; the catalog is in better shape than the contrarian implies.

---

## What's still open

The swarm flagged but the v2.6 pass did NOT fix:

1. **No actual Pi 5 measurement.** The 5× projection factor is industry-standard but unmeasured. v3+ work.
2. **No E2E CLI smoke tests.** All 110 tests are unit-shaped. ~30 LOC to add; not done in this audit.
3. **arXiv citations in BITDISTILL_PLAN.md still unverified.** Caveat box added but verification deferred.
4. **MultiPL-E-`.atm` shard not built.** Cross-language benchmark would test against an external standard.
5. **Several MEDIUM-severity code-critic findings** (`DROPPED_IMPORT_MODULES` dead code, unused `name` params in inline fast paths, duplicated UTF-8-stdout setup) deferred as low-priority hygiene.

---

## Verdict

**v2.6 is the work after honest measurement.** v2.0's "30× latency headroom" became ~1.2×. v1.5's "3.82× density on lowerer-emitted .atm" was actually measured on hand-written aspirational text; honest measurement on lowerer output is ≥2× but corpus-dependent. The IR reframe makes every choice well-motivated where the source-language framing left them open to attack.

The swarm pass took ~30 minutes wall-clock, found 9 critical bugs the prior self-audit missed, and forced a reframing that cost zero code but recasts every architectural decision as well-motivated.

**Lesson going forward**: hostile multi-agent review is cheaper and finds more than self-audit. Do it earlier and more often.
