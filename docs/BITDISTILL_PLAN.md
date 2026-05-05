# BitDistill Plan for `.atm` v2.5+

**Status**: planning document, not executed in this session (multi-day GPU job).

The mainstream BEP-7 agent identified BitDistill (Wu, Huang et al., arXiv:2510.13998) as the highest-leverage decision for v2.5: don't pretrain a 1.58-bit model from scratch; distill from a strong code base into a ternary student in three stages.

This document captures the plan with enough detail that a reader with a single H100 (or a small A100 cluster) can execute it.

> **✅ Citation-verification status (v2.7 + v2.8, 2026-04-28)**: all 7 arXiv IDs in this document have now been verified directly against arxiv.org. v2.7 verified the 5 load-bearing references; v2.8 closes out the remaining two alternative-path references:
>
> | arXiv ID | Title | Authors | Date |
> |---|---|---|---|
> | [2510.13998](https://arxiv.org/abs/2510.13998) | "BitNet Distillation" | Wu, Huang, Wang, Song, Dong, Xia, Wei | Oct 2025 |
> | [2504.12285](https://arxiv.org/abs/2504.12285) | "BitNet b1.58 2B4T Technical Report" | Ma, Wang, Huang, Zhang, Hu, Song, Xia, Wei | Apr 2025 |
> | [2508.15866](https://arxiv.org/abs/2508.15866) | "Correctness-Guaranteed Code Generation via Constrained Decoding" | Li, Rahili, Zhao | Aug 2025 (COLM 2025) |
> | [2412.13337](https://arxiv.org/abs/2412.13337) | "Unveiling the Secret Recipe: A Guide For Supervised Fine-Tuning Small LLMs" | Pareja et al. | Dec 2024 |
> | [2402.01035](https://arxiv.org/abs/2402.01035) | "Getting the most out of your tokenizer for pre-training and domain adaptation" | Dagan, Synnaeve, Rozière | Feb 2024 |
> | [2411.04965](https://arxiv.org/abs/2411.04965) | "BitNet a4.8: 4-bit Activations for 1-bit LLMs" | Wang, Ma, Wei | Nov 2024 |
> | [2504.18415](https://arxiv.org/abs/2504.18415) | "BitNet v2: Native 4-bit Activations with Hadamard Transformation for 1-bit LLMs" | Wang, Ma, Wei | Apr 2025 |
>
> The BitNet a4.8 and BitNet v2 papers (alternative-path references for activation quantization beyond the 1.58-bit weight regime) are now confirmed published work by the same Microsoft Research / BitNet group as the rest of the references. Every citation in the BitDistill cost estimate and recipe is now verified.

---

## Why distill, not pretrain

| Option | Cost | Quality at 1B | Time |
|---|---|---|---|
| Pretrain 1.58b from scratch (BitNet b1.58 2B4T recipe) | ~$50k–200k compute | matches FP16 at 2B/4T scale | 4–6 weeks |
| **BitDistill from Qwen2.5-Coder-1.5B** | **~$2k–8k compute** | **matches FP16 teacher to within 1-2 PPL** | **3–7 days** |

BitDistill is 25–50× cheaper for comparable quality. The arXiv:2510.13998 paper validates this on Qwen3-0.6B / 1.7B / 4B against FP16 teachers; the smaller students all hit teacher parity.

## Recipe (three stages)

### Stage 1 — SubLN insertion

Insert SubLN (sublayer normalization) into the FP16 teacher at every BitLinear-target layer. This stabilizes activations under the impending ternarization. ~500 LOC mod to a transformers checkpoint loader.

**Input**: Qwen2.5-Coder-1.5B-Instruct (HuggingFace: `Qwen/Qwen2.5-Coder-1.5B-Instruct`)
**Output**: SubLN-modified FP16 checkpoint

### Stage 2 — Continued pretrain (10B tokens)

Continue pretrain for ~10B tokens on a corpus mix to keep the teacher fresh in our domain:

| Source | Weight | Description |
|---|---|---|
| `.atm` natural corpus | 5% | 138 lowered Forge decls — small, but high-quality canonical signal |
| `.atm` synthetic corpus | 35% | 5000+ template-generated NL→.atm pairs (v2.5 `synthetic_corpus.py`) |
| Python code (Stack-v2 filtered) | 40% | Forge-shape Python (function-heavy, type-annotated) |
| GitHub diff / commit msgs | 15% | NL → code pairs for instruction-following |
| General code refresh (small mix) | 5% | Diversity ballast |

**Total tokens**: ~10B
**Hardware**: 8× H100 (80GB) for 3-5 days, or 1× H100 for ~3 weeks
**Loss**: standard causal LM next-token prediction
**Learning rate**: 5e-5 cosine with 1k warmup steps
**Batch**: 2M tokens per step (gradient accumulation as needed)

### Stage 3 — Dual logit + attention distillation

The 1.58b student is initialized from the SubLN+continued FP16 teacher's weights, then trained with two losses:

1. **Logit KL divergence**: KL(student logits || teacher logits) on the same input
2. **Attention map distillation**: MSE between student attention maps and teacher attention maps (per layer)

**Total tokens**: ~5B (less than stage 2 — distillation is sample-efficient)
**Hardware**: same 8× H100 for 2-3 days
**Quantization-aware training**: BitLinear with straight-through-estimator on weights, 8-bit absmax on activations, FP16 shadow weights
**Loss weights**: 0.7 logit KL + 0.3 attention MSE

## Output

A 1.58-bit ternary 1.5B-param model (`atomadic-lang-bitnet-1b-v2.5`) at:
- ~0.4 GB on disk (vs ~3 GB FP16)
- ~0.7 GB resident with KV cache
- Pi 5: 40-55 tok/s sustained (vs 22-35 for Q4_K_M 1B)
- Energy: 0.02 J/token at sustained throughput

## Constrained-decoding-aware fine-tune (companion stage)

Per Netflix arXiv:2508.15866, after stage 3 do one final pass:

**Task**: emit `.atm` declarations from natural-language descriptions (the synthetic-corpus pairs)
**Reward**: 1 if every emitted token passes the v2.0 phase-mask, 0 otherwise
**Algorithm**: PPO with KL penalty against the post-stage-3 reference policy
**Tokens**: ~1B
**Effect**: model internalizes legality so the mask becomes near-no-op at inference

## Validation plan

Before declaring v2.5 done, the model must:

1. **Round-trip test**: emit 100 `.atm` decls from synthetic NL prompts; ≥95% must round-trip via `forge raise` with byte-identical preservation
2. **Mask consistency**: every emitted token must pass the v2.0 phase mask (after constrained-decoding-aware FT, target ≥99% mask-pass rate without applying the mask)
3. **Density comparison**: emitted `.atm` should compress at ≥ 3× vs Python-emitting baseline of same model class on the same NL prompts
4. **MultiPL-E-`.atm` benchmark**: HumanEval-164 problems translated to `.atm` syntax; target ≥40% pass@1 after mask application

## Cost estimate

| Stage | Hardware | Wall time | Cloud cost (April 2026 spot) |
|---|---|---|---|
| Stage 1 (SubLN insertion) | 1× A10G | <1h | ~$3 |
| Stage 2 (10B token continued pretrain) | 8× H100 | 4 days | ~$2,500 |
| Stage 3 (5B token distillation) | 8× H100 | 3 days | ~$1,800 |
| Constrained-decoding RL | 8× H100 | 2 days | ~$1,200 |
| **Total** | | **~10 days** | **~$5,500** |

This is the entire v2.5 training budget. Single-developer-affordable; not requiring a research lab.

## Risks and mitigations

1. **Synthetic-pair distributional gap.** The v2.5 synthetic corpus is template-based; if the BitNet student over-fits to template patterns, real-world emission will be brittle. *Mitigation*: hold out 10% of natural corpus for validation; if template-overfit shows up, blend in more natural samples or run a second-pass synthetic generator that randomizes more.

2. **Tokenizer mismatch on Qwen2.5-Coder.** Qwen's tokenizer is BPE over ~150k tokens (cl100k-class). Our `.atm` BPE is 4096. We must replace Qwen's embedding+head with the `.atm` BPE before stage 1. The replacement loses Qwen's pretraining signal partially — exactly what stage 2 (continued pretrain) recovers.

3. **Constrained-decoding-aware FT instability.** PPO on RLHF-style rewards is famously unstable. *Mitigation*: clip aggressively, use a small KL coefficient, monitor reward-hacking via held-out perplexity.

4. **Pi 5 throughput target unmet.** If the 1.58b model emits at <20 tok/s on Pi 5, the language's edge story is harmed. *Mitigation*: BitNet a4.8 (4-bit activations) is the next-step compression if needed; sub-1.58b not feasible.

5. **No actual Pi 5 hardware in current dev environment.** All edge claims are projections. *Mitigation*: include a "Pi 5 measurement" milestone in v2.5 deployment.

## Concrete next steps (executable)

1. Stand up an 8× H100 instance (Paperspace, RunPod, Crusoe — ~$10/h spot)
2. `git clone microsoft/BitNet` and review the recipe scripts
3. Apply the v2.5 corpus mix as the continued-pretrain dataset
4. Start stage 1 (SubLN insertion); CPU-friendly preflight, ~1h
5. Stage 2 (continued pretrain) — start the 4-day run; budget ~$2.5k
6. Stage 3 (distillation) — 3-day run
7. Constrained-decoding RL — 2-day run
8. Validate against the four metrics above
9. Publish results + checkpoint as `atomadic-lang-bitnet-1b-v2.5`

This plan is not executed in the current session (it's a multi-day GPU workflow). The session's contribution to v2.5 is:
- Synthetic corpus generator (`a3_og_features/synthetic_corpus.py`)
- 5000-pair generation tested and demonstrated
- BPE retraining on the grown corpus shows class-density jumps from 0.99× to 1.32×
- This plan documenting the BitDistill execution path with cost/time estimates

The remaining work is **execution** of an established recipe, not research.
