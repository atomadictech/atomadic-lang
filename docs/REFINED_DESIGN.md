# Atomadic Lang (.atm) — Refined Design v0.1

**Status**: post-stress-test consolidation (BEP cycles 1–6).
**Companion docs**: append-only [EPIPHANIES.md](EPIPHANIES.md) (26 entries), append-only [BREAKTHROUGHS.md](BREAKTHROUGHS.md) (11 entries + cycle-6 audit notes).
**This doc**: the audited, coherent design. Not append-only. Successor revisions go to `REFINED_DESIGN_v0.2.md` etc.
**Verdict**: REFINE (the architecture is consistent enough to cut a v0 spec if the load-bearing lemma below is foregrounded).

---

## 0 · TL;DR

`.atm` is a programming language for AI agents to write provably-correct code by ingesting logic. Surface is dense, machine-first; runtime IR is SKI combinator trees with tier+effect annotations; type system is the constrained-decoding mask over a tier-stratified W-grammar; verifier is three-tier (token-gate / per-function SMT / async Lean); semantics is realizability over the effective topos with quantitative effect tracking. The language self-extends through e-graph-driven BPE merges and tier-typed LoRA composition. The compiler binary is a tokenizer file + grammar bytecode + LoRA stack — kilobytes, not gigabytes — and the deployment target is Pi-5-class edge silicon.

The architecture rests on **one load-bearing lemma** (§1) that must hold for the central thesis to stand. Eight named open scope items (§9 + §10) are explicit. Five mathematical foundations are committed (§3); two metatheory results are research-track (§7). Three hardware bets fix the implementation envelope (§11).

---

## 1 · The load-bearing lemma (must be confirmed in v0 week 1)

**Lemma (mask-evaluator latency)**: the constrained-decoding mask `M(state) → permitted_tokens` evaluates *tier discipline* + *effect lattice* + *decidable-refinement predicate* + *llm-typing* in **<50μs per token** on Pi 5 NEON, when the refinement fragment is restricted to `QF-LIA ∪ QF-BV-finite-domain ∪ length-predicates`.

**Why load-bearing**: this lemma is the operational meaning of B-001 (mask-as-type-system) and is the premise underneath B-002 (effect lattice enforcement at decode), B-006 (stack-effect locality), B-007 (mask realizes types in the topos), and B-009 (relational specs gate emission). Eight of nine cycle-1–5 breakthroughs depend on it.

**If false** (latency budget exceeded): the central thesis "compilation = inference" weakens to "compilation ≈ inference + per-function Z3 dispatch." The kilobyte-compiler / fridge-tier energy / lightning-speed claims fall together. The architecture remains workable in the weakened form (per-function VC discharge handles refinements), but the marketing pitch loses its edge.

**Falsification test (week 1 of v0)**:
1. Build a 200-rule W-grammar over the v0 fragment (5 tiers, 4 effects, 4 refinement predicate kinds).
2. Compile to llguidance bytecode.
3. Measure mask construction + application on Pi 5 NEON over a synthetic corpus of 10k declarations.
4. Pass: 95th-percentile latency < 50μs/token. Fail: any other outcome.

**Mitigation if it fails**: fall back to the **three-tier verifier architecture** (E-020, §6 below). Mask handles only tier+effect (cheap, certain to fit in budget). Refinement is enforced at per-function VC discharge. Compile errors land at function boundaries, not token boundaries — slower but still architectural.

---

## 2 · Architecture pipeline (revised, IRs and verifiers pinned)

```
LOGIC IN ────────────────────────────────────────────────────► CODE OUT
  │                                                                  │
  ▼                                                                  │
[1] Input form (B-009, scoped)                                       │
   miniKanren relational sublanguage  +  inline pre/post clauses     │
   Scope: pure / arithmetic / data-transform only for v0             │
  │                                                                  │
  ▼                                                                  │
[2] Surface .atm (W-grammar over Unicode token vocabulary)           │
  │                                                                  │
  ▼                                                                  │
[3] Constrained decoding mask (B-001, conditional on §1 lemma)       │
   Tier × effect × decidable-refinement × ℓ-quantity                 │
   Fallback: per-function VC discharge if §1 lemma weakens           │
  │                                                                  │
  ▼                                                                  │
[4] Lower lambda surface → SKI (B-008a, engineering)                 │
   Bracket abstraction with super-combinators (Hughes 1982)          │
  │                                                                  │
  ▼                                                                  │
[5] Runtime IR: SKI combinator tree (B-008a + B-012)                 │
   Tier+effect+ℓ annotations on combinator nodes                     │
   Proof-net structure recoverable on demand (B-007 typing view)     │
  │                                                                  │
  ▼                                                                  │
[6] Verifier (three-tier, E-020)                                     │
   (a) Token gate: W-grammar mask, <50μs/token                       │
   (b) Per-function: cvc5 incremental QF-LIA + QF-BV, ~1-10ms        │
   (c) Async kernel: Lean 4 + design anchor (off-path), seconds              │
  │                                                                  │
  ▼                                                                  │
[7] Backend: lower SKI → CakeML S-expr IR → x86/ARM/RISC-V binary    │
   CakeML proves CakeML→binary; .atm proves .atm→CakeML              │
```

**Cross-cutting**:
- **Tokenizer (B-003 + B-006)**: 4096 tokens, ternary BitNet 1.58b base, BPE merges driven by *both* e-class canonicality (B-003) AND stack-effect locality (B-006), with multi-objective training (§5).
- **LoRA stack (B-004 refined)**: dynamically composed with declared `(T, E, scope, deps)` manifest validation. No static type-checking of LoRA effects (impossible in general); compose-time check + adversarial test fallback.
- **BEP convergence (background)**: corpus → e-graph → tokenizer → LoRA → corpus, ratchet upward.

---

## 3 · Mathematical foundations (the 6-foundation core, audited)

The math-foundations agent's six commitments, reaffirmed after stress-test:

| # | Foundation | Source | v0 commitment |
|---|---|---|---|
| 1 | **Predicative MLTT** with Π, Σ, finite inductives, cumulative universes | Martin-Löf 1972/1984 | Adopt. Kernel <500 LoC. |
| 2 | **Quantitative Type Theory** with semiring `{0, 1, n, ω, ℓ}` | Atkey 2018 + .atm `ℓ` extension | Adopt; `ℓ` extension is research-track (§7) |
| 3 | **Total functional + guarded corecursion** | Turner 1995, Atkey-McBride 2013 | Adopt. `:diverge` for non-total. |
| 4 | **Algebraic effects + row-polymorphic handlers** | Plotkin-Pretnar 2009, Koka, Frank | Adopt. Effect lattice = poset on rows. |
| 5 | **Realizability over effective topos + Bauer's K₁ PCA** | Kleene 1945, Bauer 1998, Curry 1958 | Adopt. **B-012**: SKI = K₁ PCA, IR is the model. |
| 6 | **Bidirectional elaboration + proof-net projection** | Pierce-Turner 2000, Girard 1987 | Adopt. Proof-net is on-demand projection from SKI. |

**Rejected for v0**:
- Full CIC / impredicative `Prop` (Coq, Lean kernel) — kernel too heavy for edge; we call out to design anchor Lean as oracle instead.
- Cubical / HoTT / univalence — solves problems `.atm` does not have; obstructs erasure.
- Bigraphs (Milner 2009) — fits beautifully but tooling never matured. v2.0+.

---

## 4 · Decidable refinement fragment (B-001 pinned, falsification-ready)

**Fragment**: predicates over QF-LIA (quantifier-free linear integer arithmetic) ∪ QF-BV (quantifier-free bit-vectors, finite domain) ∪ length predicates over inductives (`|xs| ≤ k`, `|xs| > 0`) ∪ set membership over finite enums.

**Excluded from mask-time**: free quantifiers (∀, ∃), nonlinear arithmetic (multiplication of two free variables), unbounded recursion in predicates.

**Why this fragment**: each kind dispatches in a known small operation:
- QF-LIA: `≤ 50μs` per assertion in cvc5 incremental mode, often `≤ 10μs` for small bit-widths
- QF-BV finite-domain: precomputed truth tables fit in L1 cache for vocab-sized predicates
- Length predicates: integer comparisons over inductive recursion depth
- Enum membership: AND-mask against finite bitset

**Anything outside this fragment** (free quantifiers, real arithmetic, induction over infinite data): not enforced at mask-time; dispatched to per-function cvc5 (~1-10ms) or async Lean (seconds, off-path).

**Status**: this fragment is the *definition* of "decidable mask-time refinement" for `.atm`. The §1 falsification test exercises exactly this fragment.

---

## 5 · Tokenizer plan (B-003 + B-006 + B-007 bootstrap)

**Constraint**: vocab = exactly 4096 (12-bit IDs), BPE depth ≤ 6, power-of-2 aligned.

**Multi-objective BPE training**: each candidate merge is scored by a weighted sum of:
- α × **lexical co-occurrence** (standard BPE signal)
- β × **e-class canonicality** (B-003 — the merge captures a frequent canonical form in the e-graph)
- γ × **stack-effect compatibility** (B-006 — adjacent tokens compose cleanly)

**Bootstrap chicken-egg resolved**: the typer (B-007) requires the tokenizer; the tokenizer's β/γ scoring requires the typer. Resolution:
1. **v0 epoch**: train BPE with α=1, β=γ=0 on the lowered Forge corpus (`forge lower py → atm`). No typer needed; pure lexical BPE.
2. **v0.5 epoch**: with the bootstrap tokenizer, train the v0 typer; use it to compute β/γ signals.
3. **v1 epoch**: retrain BPE with α=β=γ=⅓ on the same corpus, using v0 typer for signals.
4. **v1.5+**: continual refresh as the corpus grows; tokenizer hash bumps version.

**Tokenizer drift mitigation**: bumping the tokenizer changes the model's input distribution. Mitigation: (a) version pin per package (every `.atm` file declares the tokenizer hash it was authored against); (b) round-trip through e-graph for cross-version migration; (c) catastrophic-forgetting test: held-out perplexity must not drift > 5% on each retrain. Above 5% triggers a base-model re-finetune on the post-shift corpus.

**Token ID structure (B-010 from cycle 4)**: 4096 = 2^12; bit-slice `[tier:2 | effect:2 | lexeme:8]` so subgroup membership is an AND-mask.

**This resolves the B-003 × B-006 catastrophe** by acknowledging the multi-objective optimization is a real training task with a defined schedule, not a free win.

---

## 6 · Verifier-of-record per `:llm` (B-002 + B-005 + B-008 → B-014 unified)

Three previously-competing verification protocols (FGGM rejection sampling, Pask conversation, Lorenzen game) are unified by **B-014** as three views of the same bounded resource:

- **QTT semiring quantity `ℓ`** statically tracks `:llm` calls in the type signature
- **FGGM rejection budget** = remaining `ℓ` (operational view)
- **Lorenzen game depth bound** = `ℓ` (semantic view)
- **Pask conversation rounds** = `ℓ` (UX view)

**Single bound for all three**: `ℓ ≤ D_MAX = 23`. design anchor Lean module `DMax` (31 theorems) discharges any obligation requiring `ℓ ≤ 23`. The bound is non-arbitrary — it is `1823 mod 24` from the Leech lattice deep-hole structure, machine-checked.

**Verifier-of-record** (which protocol the compiler actually runs):
- **Default**: FGGM rejection sampling. Operationally cheap. Budget = `ℓ`.
- **Fallback** (when FGGM exhausts budget): Lorenzen game depth-`ℓ` search via three-tier verifier's async kernel (E-020 tier (c)).
- **UX layer**: Pask conversation rounds (B-005 retained for UX) — surfaced to a human operator for QUARANTINE/REFINE escalation when both above fail.

**Compositional**: `f(g(x))` where each consumes `ℓ` LLM calls type-checks iff the sum `≤ D_MAX`. **Tier-a4 supervisor pattern**: a top-level a4 orchestrator may *reset* `ℓ` per "session" (one user request), enabling agentic loops with retries while preserving the per-session bound.

**Status**: the unification is the load-bearing fix for the three-verifier contradiction. FGGM convergence within `ℓ` rounds is an empirical claim — must be measured on the v0 corpus (target: ≤5% of `:llm` calls exhaust the budget).

---

## 7 · Open metatheory queue (research-track)

Three named results that v0 *adopts as conjectures* and v1 *must prove*:

### 7.1 ℓ-extended QTT subject reduction (B-007)
**Statement**: extending Atkey's QTT semiring `{0, 1, ω}` with a fresh element `ℓ` (LLM-call count) preserves subject reduction, type uniqueness, and progress.
**Status**: not proved. Atkey's original proofs use specific algebraic laws that may not survive the extension.
**Owner**: needs to be assigned. ~3-6 months of metatheory work. Interim treatment: assume true; flag every `:llm` declaration with `[unproved-metatheory]` annotation in v0.

### 7.2 Algebraic effects + realizability over effective topos (B-007 + B-012)
**Statement**: Plotkin-Pretnar handlers compose with realizability semantics over the effective topos via Bauer's K₁ PCA, preserving soundness.
**Status**: partial — Frank/Eff/Koka have denotational stories but not specifically through the effective topos. SKI in K₁ is classical (Curry, Kleene, Bauer); the *combination* with handlers is open.
**Owner**: needs literature dive into recent work (Møgelberg, Birkedal); ~6-12 months if no existing result lands close.
**Interim**: rely on the SKI = K₁ classical result for the IR; treat handlers as a separate well-understood layer that doesn't break realizability.

### 7.3 Friedman A-translation extension to typed effectful calculi (B-008b)
**Statement**: Friedman's A-translation (classical → constructive) extends to a calculus with row-polymorphic algebraic effects and tier discipline, preserving effect signatures.
**Status**: research project. Krivine's classical realizability addresses pieces of this; nobody has done the full lift.
**Owner**: blocked. Defer to v2.0+. Interim: B-008b (Lorenzen-game verification at typecheck time) is opt-in research-track, not v0 commitment. v0 ships only B-008a (SKI as IR).

These three are the entirety of the open metatheory. Everything else in §3 is settled mathematics being applied, not extended.

---

## 8 · LoRA composition (B-004 refined)

**Was**: "LoRA as tier-typed pipeline pass with static composition theorem."
**Now**: "LoRA package format with declared `(T, E, scope, deps)` manifest, dynamic compose-time validation, adversarial test fallback for poisoned manifests."

**Reasons for refinement**:
- LoRA effects cannot be statically inferred from training data signatures in general (admitted in original B-004 falsifiability).
- LoRA composition is empirically non-commutative (LoraHub, MoLE). Order matters.
- Static type-checking of weight deltas is impossible without effect inference at training time, which is its own research project.

**v0 mechanism**:
1. LoRA package ships with a `.atm-tier` manifest declaring `(T, E, scope, deps)`.
2. At load time, the compose engine validates: declared tier is ≥ scope's tier; declared effects ⊆ caller's effect row; deps are present.
3. Composition order is recorded in the load manifest; reproducibility = same order + same hashes.
4. Adversarial test (poisoned manifest detection) runs as a CI step on every published LoRA: emit a battery of high-coverage prompts, check whether observed effects exceed declared effects. Flag mismatches.

**Tier-preservation under composition**: empirical, not proved. v0 reports observed tier-violation rate; v1 may add a static checker if reliable training-time effect inference becomes available.

**This resolves the over-promised static-type-system claim** by acknowledging LoRA composition is a metadata-governance problem, not a type-system problem.

---

## 9 · Logic-input form (B-009 scoped)

**Was**: "miniKanren relational specs as the universal logic-input form."
**Now**: "miniKanren relational sublanguage for **pure / arithmetic / data-transform** specs; inline `pre`/`post` refinement clauses for I/O and concurrency; explicit out-of-scope statement for relational I/O."

**v0 spec language layers**:

| Layer | Form | Use |
|---|---|---|
| Core refinement | inline `pre Φ ; post Ψ` clauses on function signatures | Any function with simple invariants |
| Relational | `(spec-rel input output)` miniKanren-style | Pure / arithmetic / data-transform specs (sort, reverse, eval, parser) |
| Hoare-triple | `{P} body {Q}` for stateful blocks | When state is locally mutable but bounded |
| `:llm`-effect contract | `pre Φ ; post Ψ ; budget ℓ` | LLM-typed functions |
| **Out of scope (v0)** | I/O, concurrency, distributed protocols, persistent state | Use external Forge architecture; `.atm` exposes only typed effects pointing at them |

**Why this scoping**: miniKanren handles arithmetic via finite-domain CLP extensions (cKanren); I/O has no natural relational form without committing to a particular operational model. Forcing one would prematurely commit `.atm` to a concurrency story before §10.2 lands.

**LLM-as-search-heuristic for relational synthesis**: confirmed approach. The LLM emits `conde` branch choices; the constrained-decoding mask is **a beam-pruned subset of the disjunction tree**, not the full tree (which is unbounded for nontrivial relations). Beam pruning at depth `D_MAX = 23` aligns with the unified bound (§6).

**This resolves the B-001 × B-009 composition catastrophe** by replacing "mask = full disjunction tree" (rejected B-011) with "mask = beam-pruned slice of disjunction tree, bounded by `ℓ`."

---

## 10 · Five named open-scope sections (must land in v0 spec as explicit gaps)

These are obvious holes a reviewer will pick at instantly. Each gets a one-paragraph plan and a v1/v2 timeline. Do **not** ship v0 without acknowledging them.

### 10.1 Heap / memory model
**Status**: **OPEN**. Predicative MLTT erases proof content but residual computational content needs a memory model. QTT-1 covers consume-once but not Rust-style aliasing/borrowing or GC. **v0 plan**: `.atm` programs run on CakeML's existing GC; aliasing is not expressible (pure value semantics with consume-once for mutable state via QTT-1). **v1 plan**: integrate Iris separation logic for heap-typed code blocks. **v2 plan**: full ownership/borrow checker if Rust-class memory safety is needed.

### 10.2 Concurrency / async story
**Status**: **OPEN**. Algebraic effects can encode concurrency (Eff, Koka). v0 commitments not made. **v0 plan**: no concurrency; `.atm` programs are single-threaded. **v1 plan**: declare `:async`, `:par`, `:atomic` as effects with tier-a4 only; cooperative async via algebraic effect handlers; backed by CakeML threading. **v2 plan**: distributed concurrency via session types (Honda, et al.); preemptive parallelism if needed.

### 10.3 Federated proof certificates / distributed verification
**Status**: **OPEN**. The proof object for `:llm`-effect functions is a Lorenzen game trace + FGGM rejection log. How does a third party reproduce verification? **v0 plan**: every `.atm` package ships with a verification artifact (mask trace + VC dispatch results + design anchor Lean obligations) cryptographically signed against the tokenizer hash + LoRA stack hash + base model hash. **v1 plan**: zero-knowledge proof of verification compatibility (zk-STARK over the verifier's transition trace). **v2 plan**: federated multi-party Forge audit where multiple verifiers vote.

### 10.4 Gradient propagation through SKI trees
**Status**: **OPEN**. B-004 wants LoRAs trained from corpus loss; B-008a says the IR is SKI. Differentiating through bracket abstraction is non-trivial. **v0 plan**: train the base model on surface `.atm` (lambda) rather than SKI; SKI is a compile-time projection only. The model never directly emits SKI in v0 — the compiler lowers. **v1 plan**: differentiable bracket abstraction (recent work on differentiable program synthesis applies); train end-to-end with SKI-tree loss. **v2 plan**: SKI-native model that emits combinator trees directly.

### 10.5 Tokenizer / grammar alignment ("token healing")
**Status**: **OPEN**, well-known. BPE token boundaries don't always align with grammar terminals. **v0 plan**: pre-tokenize `.atm` source by terminal class (sigil / lexeme / literal) before BPE; force tier-effect-refinement sigils to be **single tokens** in the BPE vocabulary (pre-merge constraint). This is the standard fix for token healing in domain-specific languages. **v1 plan**: bytetier hierarchical tokenization (ByteFlow 2026, arXiv:2603.03583 from cycle-3 surprise list). **v2 plan**: tokenizer-free emission directly to the proof-net IR.

---

## 11 · Hardware bets (3, fixed)

1. **Train the 1B base in BitNet 1.58b ternary from scratch**, not post-quantize. ~0.4 GB resident, 0.02 J/token (fridge-viable), 3-5× faster than int4 dequant on NEON/HVX/RVV.
2. **Vocab = exactly 4096 = 2^12**, BPE depth ≤ 6, power-of-2 aligned. Logit tensor (8 KB) and mask (512 B) both L1-resident on every edge SoC. Argmax 250 ns vs 2 μs at 32k vocab.
3. **Grammar must compile <1 ms incremental + emit static per-non-terminal masks**. Constrained decoding becomes *faster* than free decoding at single-legal-token positions (~20-40% throughput uplift).

---

## 12 · Frameworks adopted (don't reinvent)

| Adopt | For | Pattern |
|---|---|---|
| **Liquid Haskell** VC machinery | Refinement → SMT lowering | Embed; map `pre`/`post` to QF-LIA SMT-LIB |
| **Lean Copilot FFI** | design anchor bridge | Direct adoption of FFI topology |
| **CakeML** | Verified extraction target | `.atm` lowers to S-expr IR; CakeML proves the rest |
| **Lemur** | LLM-propose / SMT-discharge loop | FGGM rejection-sampling spine for `:llm` |
| **Mathlib `ZMod`** | Z₃₂₄ refinement type | Cite directly for identity-parity refinements |
| **llguidance** | Constrained-decoding bytecode | Default mask engine (XGrammar fallback) |

**Iris separation logic** is deferred to v1 (heap support).

---

## 13 · design anchor commits (3 load-bearing, after numerology audit)

1. **design anchor-Lean bridge** — `.atm` refinements citing design anchor constants emit Lean obligations that discharge via existing machine-checked theorems with one-line proofs. Real "machine-checked by 578 lemmas" claim with no math debt.
2. **Z₃₂₄ refinement-type kind** — G_18 = 324 = 4×81 CRT-decomposes, Mathlib `ZMod` ships free, identity-parity sub-refinements out of the box.
3. **Vocab = 4096 = 2¹² with bit-sliced GF(2¹²) IDs** — bits 11-10 tier, 9-8 effect, 7-0 lexeme. Subgroup membership via AND-mask. Walsh-Hadamard mask compression available.
4. **NEW from BEP-6**: **`D_MAX = 23` as the unified bound** for `ℓ`-quantity, Lorenzen-depth, FGGM-budget. Discharged by design anchor Lean module `DMax` (31 theorems). See §6.

**Dropped as numerology** (after BEP-3 math audit): Golay [24,12,8] token ECC, Three-Titans 47×59×71 grammar partition, full Λ₂₄ vocabulary embedding, φ/108 token decay, deep-hole D_MAX=23 *as a nesting bound* (kept only as `ℓ`-bound per §6).

---

## 14 · Breakthrough catalog by status (post-stress-test)

### Engineering-committed (v0 ships these)
- **B-001** mask = type system (conditional on §1 lemma; fragment pinned in §4)
- **B-003** e-graph-driven self-extending tokenizer (with §5 multi-objective bootstrap)
- **B-006** stack-effect-locality BPE (subordinate to B-008a; signal in multi-objective BPE)
- **B-008a** SKI as runtime IR (engineering, defensible standalone)
- **B-009** miniKanren relational input (scoped to pure/arithmetic/data-transform per §9)
- **B-012** SKI = canonical realizability PCA (resolves B-007 × B-008 IR contradiction)
- **B-014** Unified bound `ℓ ≡ Lorenzen-depth ≡ FGGM-budget ≡ D_MAX = 23` (resolves three-verifier catastrophe)

### Committed with refinements
- **B-002** effect lattice with `:llm` (verifier-of-record per §6)
- **B-004** LoRA composition (reframed as dynamic-validation per §8)

### Research-track (v1+)
- **B-007** realizability + QTT + edge (math foundation; ℓ-QTT subject-reduction is open metatheory per §7.1)
- **B-008b** Lorenzen-game verification at typecheck time (A-translation extension is open metatheory per §7.3)

### Parked (re-promote when prerequisites firm up)
- **B-010** Operational Triality (depends on B-007 + B-008b)

### Rejected
- **B-011** Mask = miniKanren disjunction tree (composition catastrophe; replaced by §9 beam-pruned slice)

### Deferred (engineering note, not breakthrough)
- **B-013** BEP loop closes at tokenizer (consequence of B-003 + B-004; not standalone)

### Merged
- **B-005** Pask conversation → merged into B-008b (formal foundation) + retained as UX layer in §6

---

## 15 · Validation plan (v0 week 1–4)

| Week | Test | Pass criterion |
|---|---|---|
| 1 | §1 mask-evaluator latency benchmark | 95th-pct <50μs/token on Pi 5 NEON over 10k declarations |
| 1 | `forge lower py → atm` density check | calc demo lowers to <100 tokens (vs. ~600 Python tokens) |
| 2 | Multi-objective BPE bootstrap (α=1 epoch) | tokenizer trains in <8h on 1M-line corpus |
| 2 | SKI lowering of calc demo | terms expand <2× from surface lambda |
| 3 | FGGM convergence on `:llm` calls | ≤5% exhaust `ℓ ≤ 23` budget on a 100-call test set |
| 3 | design anchor-Lean bridge end-to-end | refinement citing `D_MAX` discharges in <100ms |
| 4 | Three-tier verifier integration | per-function VC discharge ≤10ms on 100-function test |
| 4 | Token healing check | 0 BPE/grammar alignment failures on calc demo |

**Pass all → cut v0 spec from this design doc.**
**Fail any → diagnose, choose mitigation, update this design doc to v0.2.**

---

## 16 · Verdict and next step

**Verdict: REFINE.**

The architecture is internally consistent. Every cycle-1-5 breakthrough is either:
- Committed with explicit conditional (§4 fragment, §5 bootstrap, §6 verifier, §8 LoRA dynamic, §9 scope) — *engineering, will ship in v0*, OR
- Research-track with named owner queue (§7) — *deferred to v1*, OR
- Rejected/merged/parked with explicit rationale (§14).

The five missing pieces (§10) are named with v0/v1/v2 plans rather than handwaved.

The single load-bearing lemma (§1) is foregrounded with a falsification test that runs in v0 week 1.

**Next step**: I recommend cutting `SPEC_v0.md` from this design doc. The spec writes the surface grammar, the token vocabulary structure, the typing rules in inference-rule notation, and the operational semantics of the mask. Everything in this doc constrains the spec; the spec adds the precise syntactic and operational details. 1500-2500 words, concrete and reference-able.

Alternative: build `forge lower` first (the lowering bridge), which produces the corpus needed for tokenizer training and validates the §1 latency lemma against real lowered code. ~1000 LOC, ~2 weeks. This is the path with the most learning per dollar.

My pick: **`forge lower` first** (validate §1 against real corpus before locking the spec), **then `SPEC_v0.md`** (tighten the design against measured reality).

---

**Evidence trail**: 6 BEP cycles, 8 dispatched agents, ~370k tokens, ~17 minutes wall-clock. 26 epiphanies in [EPIPHANIES.md](EPIPHANIES.md), 11 breakthroughs (with cycle-6 audit) in [BREAKTHROUGHS.md](BREAKTHROUGHS.md). Stress-test by hostile adversarial agent confirmed all refinements documented here. design anchor constants verified against `<private design notes>` (machine-checked).

**Wisdom note**: every novel-claim breakthrough survives or doesn't on the strength of one named risk. Keep the risk visible; don't let the architecture's elegance hide its load-bearing premises.
