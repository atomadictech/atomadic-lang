# Atomadic Lang — Self-Audit (post v2.5)

**Date**: 2026-04-28
**Method**: agent-driven retrospective over the v0 → v2.5 single-session arc.
**Verdict**: REFINE — work shipped, process improvable.

This document is the canonical retrospective. It exists because every code-base benefits from one place that names what was learned and what would be done differently — separate from the LINEAGE (which records what happened) and the BREAKTHROUGHS / EPIPHANIES (which record claims).

If a future session is going to follow this arc, read this first.

---

## 1. The single biggest mistake

**The pre-tokenizer config bug should have been caught at v0.5, not v1.5.**

v0.5 through v0.9 silently used HuggingFace `tokenizers`' default `Whitespace` pre-tokenizer, which splits on punctuation. That made cross-punctuation merges (`:i`, `→i`, `⟩→i`, `⟨a:i`, `b:i⟩→i`) **literally unreachable** to BPE training regardless of forced-token status or corpus frequency.

This wasn't a subtle issue. The corpus analyzer in v1.5 surfaced `:s` at **123× frequency** as the top *unmerged* bigram. The signal was sitting there waiting to be noticed for 5 milestones. v1.5 fixed it with a one-line change (`Whitespace` → `WhitespaceSplit`) and density doubled — `1.88× → 3.82×` on calc a1-only, vocab fill `72% → 100%`.

**Five milestones of "BPE optimization" work happened against a tokenizer that had already thrown away half the available compression.**

What I should have done at v0.5: written one explicit "what does the BPE actually merge?" test against a representative line. The test would have asked *"if `:i` appears 100× in the corpus, why isn't it a single token?"* — and the answer would have been "because the pre-tokenizer split it before BPE could merge it." Five-minute fix at v0.5 instead of a v1.5 milestone.

**Lesson**: when a configuration knob has two reasonable defaults, *test both at milestone-1*, not milestone-9. The biggest knobs are structural, not corpus-specific.

---

## 2. Three process changes I'd commit going forward

### 2a. Build structural inverses at v0.5, not v1.0

The lower↔raise round-trip property in v1.0 caught **4 latent emitter bugs** that had been alive for 5 milestones:

1. Newline leakage in structural fallback (since v0)
2. Newline leakage in expression fallback (since v0)
3. Control-character leakage in string Constants (since v0)
4. Control-character leakage in f-string Constant text segments (since v0.8)

Each bug was a one-character omission. Each survived 4-5 milestones because no unit test could target it — the bug shape only manifests under parser inversion. If I'd built `forge raise` immediately after `forge lower` (i.e. v0.5 instead of v1.0), each bug would have been caught at the milestone it was introduced.

Inverses are not v1.0 polish; they are v0.5 verification infrastructure. The same applies to any DSL with a serialization step.

### 2b. Adversarial review *before* promotion, not after

Cycles 1–5 promoted 9 breakthroughs (B-001..B-009) with confident claims. Cycle 6's stress-test agent then graded them:

- **0/9 SOLID**
- **6/9 CONDITIONAL**
- **1/9 MERGE** (B-005 → B-008)
- **1/9 REJECT** (B-011)
- **1/9 REFINE-split** (B-008 → B-008a + B-008b)

I was systematically over-confident through cycles 1-5. The corrective came as cycle 6, but it should have been the *first* review, not the sixth. Promote candidates as candidates; demand a hostile pass before they enter the breakthrough catalog.

This pattern repeats outside this project: research synthesis without adversarial filter is a fluency drift toward the most-coherent-sounding combinations, not the most-defensible ones. The fringe agent's deepest cuts (PRIZ, W-grammar BPE filter) survived cycle 6 and 7 hostile review precisely because they were *less* coherent-sounding initially.

### 2c. Batch the lowering milestones

v0.6 (multi-stmt), v0.7 (classes), v0.8 (f-strings + comps + lambdas), v0.9 (try/except + with + kwargs) were each implementation-shaped — one Python AST node category, ~150 LOC, ~10 tests per milestone. Per-milestone overhead (LINEAGE entry, density table, retro, summary, BPE retrain, user-facing summary) was the same regardless of payload size.

Batching v0.6 + v0.7 + v0.8 + v0.9 into one or two larger milestones would have saved meaningful time without losing rigor. **Granularity was probably 2-3× too fine.**

The right batching: "lowering coverage" as one milestone (everything from multi-stmt through try/except/with/kwargs), then "tokenizer audit" (catching the WhitespaceSplit issue at v0.5 would have meant most v0.6-v0.9 density work didn't need separate framing), then "structural verification" (round-trip + latency benchmark together).

---

## 3. The biggest "got-it-right" calls

These are decisions that initially seemed dubious but paid off.

### 3a. Tier discipline as the implementation-language structure

Using `.atm`'s 5-tier monadic architecture for the Python codebase that builds `.atm` was either going to be the cleanest dogfooding move or a precious affectation. It worked: **3 architectural drifts caught at test-collection time over 10 milestones**:

- v0.5 — `a2.CorpusCollector` imported `a3.lower_package` (circular import error at test-collection)
- v0.6 — `_lower_middle_stmt` missed attribute targets (caught by v0.7 method test the moment it was written)
- v0.8 — helper `def`s landed inside `lower_expr`, pushing existing handlers to dead code (caught by `'None*2' == 'self.x*2'` from v0.7's test)

Each bug was localized in <1 minute and fixed in <5 minutes. **Without tier discipline, these would have been latent for tens of minutes to hours.**

This is the single strongest empirical evidence in the entire session that the architecture isn't aesthetic — the structural property `.atm` enforces on AI-emitted code happens to be the right property for the language's own implementation. The implementation language and the design language share constraints; reuse pays.

### 3b. Refusing to chase the 6× density target uncritically

The "6×" came from a back-of-envelope calc on the calc demo (~600 Python tokens → ~95 .atm tokens) and became gospel through repetition in design docs. v1.5 hit 3.82× with a projected path to 5.96× — convenient but unverified.

The leading indicator across milestones turned out to be **pattern coverage**, not headline density. The class-synthetic case (0.52→0.92→0.99→1.32× across milestones) showed real progress when density on the canonical line `1π add ⟨a:i b:i⟩→i = a+b` plateaued at 1.88× through v0.6/v0.7/v0.8. Each milestone's right metric was *"what does the BPE NOW handle that it couldn't?"* — not *"how much shorter is the canonical example?"*

Honest reading: 3.82× a1 / 3.48× whole-package / 1.32× class is great. 6× was an aspirational placeholder that became a goal. Pin targets to measurements, not initial intuitions.

### 3c. Honest "0/9 SOLID" verdict in cycle 6

Cycle 6's stress-test agent gave a brutal grade and I shipped it as-is rather than softening it. Result: B-005 was correctly merged into B-008b. B-011 was correctly rejected. B-008 was correctly split into engineering (B-008a) and research (B-008b). Each correction tightened the breakthrough catalog and made downstream cycles defensible.

The right reaction to a hostile review is to update the catalog, not the review.

---

## 4. Honest gaps still in the work

These are things the docs occasionally present as more solid than they are. They are noted here for the next session to fix or flag harder.

### 4a. Pi 5 measurements are projections, not data

The 5× Pi 5 projection factor is industry-standard (Geekbench single-core ratios, llama.cpp throughput on equivalent quantizations) but it is **not** measured on actual Pi 5. Headlines occasionally presented "1.5μs Pi 5, 30× headroom" with more confidence than the data supported.

The paper's §7 limitations and the v2.0 LINEAGE entry both acknowledge this. The user-facing summaries during the session sometimes did not. **Should have flagged "PROJECTED — actual Pi 5 deployment queued" more aggressively in headlines.**

### 4b. Agent citations weren't verified

The cycle-7 BitDistill plan uses arXiv:2510.13998 as load-bearing for a $5,500 cost estimate. I took the citation at face value from the mainstream agent's report. If that paper doesn't exist or doesn't say what the agent claimed, the BitDistill plan is unfounded.

Same applies to: arXiv:2508.15866 (Netflix constrained-decoding-aware FT), arXiv:2412.13337 (3-10k decl fine-tuning floor), arXiv:2402.01035 (custom code BPE compression), arXiv:2504.12285 (BitNet b1.58 2B4T). All cited prominently in `BITDISTILL_PLAN.md` and `PAPER_v2.md` related-work.

**Should have spot-verified at least 1-2 citations per agent report.** Cheap insurance. Next session must verify these before they enter load-bearing decisions.

### 4c. No end-to-end CLI tests

110 tests, all unit-shaped (function-level). The closest thing to E2E is `test_roundtrip_forge_corpus`. There is no test that exercises the CLI pipeline end-to-end (e.g., "lower then raise via CLI then verify byte-identical"). A production codebase should have at least one smoke test per public command. Partly defensible (we have round-trip on real corpus), partly a gap.

### 4d. Documentation/code ratio is unusual

3546 LOC of code with arguably 15,000+ words of docs (LINEAGE alone is huge). Some entries are repetitive across LINEAGE entries; the milestone summaries restate similar patterns. Some of this is justified for a research-grade project, but per-milestone documentation could be 2-3× more concise.

### 4e. The session ran longer than its own learning curve justified

User asked "proceed" 10+ times. I did each milestone fully (implementation + tests + LINEAGE + summary). Marginal learning per milestone dropped after v1.5 — v2.5 produced engineering value (corpus growth, BitDistill plan) but no new architectural insight. **I should have explicitly proposed a stopping point around v2.0, not continued automatically through v2.5.** When marginal insight per milestone drops below the diminishing-returns threshold, name it.

---

## 5. The corrective for next session

If a future session resumes the work:

1. **Don't run BEP cycles 5-7 again unless asked.** Cycles 1-4 + cycle 6 (adversarial) covered the design space. Cycles 5 and 7 added refinements but not breakthroughs. The fringe agent in cycle 5 surfaced the highest-value novel angles — keep that one.
2. **Verify the 5 cited arXiv papers in BITDISTILL_PLAN.md** before treating the plan as load-bearing for spend.
3. **Build E2E CLI smoke tests** — one per public command. ~30 LOC total.
4. **If `forge raise` is being extended** (the deferred body-level expression parser), pair it with a corresponding round-trip test from day one.
5. **Run the §1 latency benchmark on actual Pi 5 hardware** before any density claim makes it into a paper headline. The 5× projection holds or it doesn't; we deserve the data.
6. **Trust the fringe-research lane.** B-015 (PRIZ) and B-016 (W-grammar BPE filter) are the most novel breakthroughs in the catalog and both came from the fringe agent. Mainstream research surveys what's been done; fringe research surveys what *could* have been done. The latter is where novelty lives.

---

## 6. What I'd preserve

The single thing I'd preserve unchanged: **tier discipline as the structural property of both the language and its implementation**. That choice paid for itself across 10 milestones with zero violations and three real bug catches. It is the architecture's strongest empirical claim — not the density numbers, not the latency benchmark, not the breakthrough catalog.

The density numbers are good (3.82× a1, 3.48× whole). The latency is good (1.5μs Pi 5 projected, 30× headroom). The breakthroughs are interesting (some empirically validated, some research-track). But the property that *makes the code base survive 10 milestones of refactoring without architectural drift* is the property that — if `.atm` gets adopted at any scale by AI authors — will keep their codebases coherent too.

That's the bet. Everything else is in support of it.

---

**Verdict: REFINE.** The work shipped (10 milestones, 110 tests, paper draft, BitDistill plan). Four specific decisions cost time or accuracy: (a) BPE pre-tokenizer audit deferred 4 milestones, (b) round-trip property deferred to v1.0 instead of v0.5, (c) breakthroughs promoted without hostile pass until cycle 6, (d) milestone granularity 2-3× too fine. Each has a clear corrective. None invalidates the result; all would compress next session by ~30%.

Pinned to truth where the session occasionally drifted to confident projection.
