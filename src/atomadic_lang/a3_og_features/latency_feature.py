"""Tier a3 — orchestrate the v2.0 §1 latency benchmark.

Measures the four components of the design-doc mask-evaluator latency:
1. Mask application (apply a 4096-bit bitmap to logits)
2. State transition (advance grammar state machine on token)
3. Refinement predicate evaluation (decidable fragment)
4. End-to-end (full path per token, summed)

Reports median, p95, p99 in microseconds. Compares to the §1 budget
(<50μs/token) and to projected Pi 5 NEON performance.

Imports a0, a1, a2.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any, TypedDict

from ..a0_qk_constants.bpe_config import VOCAB_SIZE
from ..a0_qk_constants.grammar_states import DECL_START
from ..a1_at_functions.mask_evaluator import (
    MASK_BYTES,
    make_mask_fn,
    precompute_phase_masks,
    transition,
)
from ..a1_at_functions.refinement_eval import (
    compile_predicate,
    eval_eq_zero,
)
from ..a2_mo_composites.bpe_trainer import load_tokenizer


# Pi 5 NEON is ~5× slower per single-thread op vs. modern x86-64 dev box.
# Sources: Geekbench single-core (~1500 vs ~3000+), llama.cpp throughput
# (35 vs 150+ tok/s for 1B Q4). 5× is a conservative midpoint.
PI5_PROJECTION_FACTOR: float = 5.0


class LatencyReport(TypedDict):
    schema_version: str
    benchmark_iters: int
    mask_application_ns: dict[str, float]
    state_transition_ns: dict[str, float]
    refinement_compiled_ns: dict[str, float]
    refinement_inline_ns: dict[str, float]
    end_to_end_ns: dict[str, float]
    pi5_projection_us: dict[str, float]
    target_budget_us: float
    verdict: str


def _stats_ns(times_ns: list[int]) -> dict[str, float]:
    """Return median / p95 / p99 / max in nanoseconds."""
    if not times_ns:
        return {"median": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    sorted_t = sorted(times_ns)
    n = len(sorted_t)
    return {
        "median": float(statistics.median(sorted_t)),
        "p95": float(sorted_t[int(0.95 * n)]),
        "p99": float(sorted_t[int(0.99 * n)]),
        "max": float(sorted_t[-1]),
    }


def benchmark_mask_application(iters: int = 100_000) -> list[int]:
    """Time how long it takes to AND a 4096-bit mask against a 4096-element logit array."""
    import array
    mask = bytes(b"\xff" * MASK_BYTES)
    # Simulate logit array with a Python array of float32-ish (we just iterate).
    logits = array.array("f", [0.5] * VOCAB_SIZE)

    times: list[int] = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        # Apply mask: zero-out logits whose mask bit is 0.
        # In production this is a vectorized NumPy / NEON op; here we sample.
        for byte_idx in range(MASK_BYTES):
            byte = mask[byte_idx]
            if byte == 0xFF:
                continue  # all permitted, skip
            base = byte_idx << 3
            for bit in range(8):
                if not (byte & (1 << bit)):
                    logits[base + bit] = float("-inf")
        elapsed = time.perf_counter_ns() - t0
        times.append(elapsed)
    return times


def _build_sparse_mask(np_module: Any, density: float = 0.10) -> Any:
    """Build a sparse boolean mask representative of real constrained-decoding loads.

    `density` is the fraction of tokens permitted in a typical phase. The v0..v0.9
    grammar has 13 phases; each permits 5–30% of the vocab. 10% is a reasonable
    representative load. (v2.6 fix — was previously all-True, which made
    np.where a no-op copy and invalidated the §1 measurement.)
    """
    np = np_module
    rng = np.random.default_rng(seed=42)
    bool_mask = rng.random(VOCAB_SIZE) < density
    return bool_mask


def benchmark_mask_application_numpy(
    iters: int = 100_000,
    density: float = 0.10,
    batch_size: int = 1000,
) -> list[int]:
    """Vectorized variant — closer to production NumPy/NEON path.

    v2.6 fixes (per swarm code-critic):
      - Mask is now sparse (10% bits set), not all-1s. Was previously measuring
        memcpy, not actual masking.
      - Timing is BATCHED — perf_counter_ns has ~100ns Windows resolution, so
        per-op timings would be timer noise. We time `batch_size` ops at a time
        and divide.
    """
    try:
        import numpy as np
    except ImportError:
        return benchmark_mask_application(iters)

    bool_mask = _build_sparse_mask(np, density=density)
    logits = np.full(VOCAB_SIZE, 0.5, dtype=np.float32)
    neg_inf = np.float32(-1e30)

    n_batches = max(1, iters // batch_size)
    times: list[int] = []
    for _ in range(n_batches):
        t0 = time.perf_counter_ns()
        for _b in range(batch_size):
            masked = np.where(bool_mask, logits, neg_inf)
        elapsed = time.perf_counter_ns() - t0
        per_op_ns = elapsed // batch_size
        # Distribute back to per-op samples for percentile stats.
        for _b in range(batch_size):
            times.append(per_op_ns)
        _ = masked  # avoid optimizer eliding
    return times


def _batched_time(fn, iters: int, batch_size: int = 1000) -> list[int]:
    """Time `fn()` calls in batches and return per-op nanoseconds.

    perf_counter_ns has ~100ns resolution on Windows. Sub-microsecond ops
    measured one at a time are dominated by timer overhead. Batching ops
    between two timer reads and dividing gives true per-op cost.
    """
    n_batches = max(1, iters // batch_size)
    times: list[int] = []
    for _ in range(n_batches):
        t0 = time.perf_counter_ns()
        for _b in range(batch_size):
            fn()
        elapsed = time.perf_counter_ns() - t0
        per_op_ns = elapsed // batch_size
        for _b in range(batch_size):
            times.append(per_op_ns)
    return times


def benchmark_state_transition(iters: int = 1_000_000) -> list[int]:
    """Time the grammar-state-machine transition function (v2.6: batched)."""
    state_box = [DECL_START]
    sample_tokens = ["1π", "add", "⟨a:i", "b:i⟩→i", "=", "a+b", "\n"]
    counter = [0]

    def _step():
        tok = sample_tokens[counter[0] % len(sample_tokens)]
        counter[0] += 1
        state_box[0] = transition(state_box[0], tok)

    return _batched_time(_step, iters)


def benchmark_refinement_compiled(iters: int = 100_000) -> list[int]:
    """Time refinement predicate evaluation — compiled-once-eval-many path (v2.6: batched)."""
    pred = compile_predicate("b≠0")
    bindings = {"b": 5}

    def _step():
        pred(bindings)

    return _batched_time(_step, iters)


def benchmark_refinement_inline(iters: int = 1_000_000) -> list[int]:
    """Time inline-fast-path refinement check (v2.6: batched, v2.7: signature update)."""

    def _step():
        eval_eq_zero(5)  # v2.7: dropped unused `name` arg

    return _batched_time(_step, iters)


def benchmark_end_to_end(
    tokenizer_path: Path,
    sample_text: str,
    iters: int = 1_000,
    include_mask_application: bool = True,
    include_refinement: bool = True,
    mask_density: float = 0.10,
) -> list[int]:
    """Time the FULL per-token mask-evaluator path per the §1 lemma.

    v2.6 fix (per swarm empirical critic): the previous version measured only
    state transition + mask lookup, omitting the components the §1 lemma names
    (mask application to logits + refinement evaluation). This version includes
    all four components per token, batched for sub-μs accuracy.

    For each token in `sample_text`, per-step timing covers:
      1. Phase-mask lookup       (always)
      2. State transition        (always)
      3. Mask application to logits via NumPy np.where  (if include_mask_application)
      4. Refinement predicate evaluation                (if include_refinement)
    """
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore

    tokenizer = load_tokenizer(tokenizer_path)
    encoded = tokenizer.encode(sample_text)
    token_ids = encoded.ids

    vocab_dict = tokenizer.get_vocab()
    phase_masks = precompute_phase_masks(vocab_dict)
    mask_for = make_mask_fn(phase_masks)
    id_to_token = {tid: tok for tok, tid in vocab_dict.items()}

    # Pre-build the realistic sparse mask + logits used in mask application.
    if include_mask_application and np is not None:
        bool_mask = _build_sparse_mask(np, density=mask_density)
        logits = np.full(VOCAB_SIZE, 0.5, dtype=np.float32)
        neg_inf = np.float32(-1e30)
    else:
        bool_mask = None
        logits = None
        neg_inf = None

    # Pre-compile a representative refinement predicate.
    if include_refinement:
        pred = compile_predicate("b≠0")
        ref_bindings = {"b": 5}
    else:
        pred = None
        ref_bindings = None

    # Token sequence repeated `iters` times — flat list for batched timing.
    state_box = [DECL_START]
    pos_box = [0]
    n_tokens = len(token_ids)
    if n_tokens == 0:
        return []

    def _step():
        tid = token_ids[pos_box[0] % n_tokens]
        pos_box[0] += 1
        tok = id_to_token.get(tid, "")
        # 1. Mask lookup
        mask = mask_for(state_box[0])
        # 2. State transition
        state_box[0] = transition(state_box[0], tok)
        # 3. Mask application to logits (the dominant cost in production)
        if bool_mask is not None and logits is not None:
            _ = np.where(bool_mask, logits, neg_inf)  # type: ignore[arg-type]
        # 4. Refinement predicate evaluation
        if pred is not None:
            _ = pred(ref_bindings)
        _ = mask  # keep mask ref alive to prevent dead-code elimination

    total_ops = iters * n_tokens
    return _batched_time(_step, total_ops, batch_size=min(1000, n_tokens * 10))


def run_full_benchmark(
    *,
    tokenizer_path: Path,
    sample_atm: str | None = None,
    iters_fast: int = 100_000,
    iters_e2e: int = 100,
) -> LatencyReport:
    """Run all four benchmark components and return a structured report."""
    sample = sample_atm or (
        "@calc\n\n"
        "1π add ⟨a:i b:i⟩→i = a+b\n"
        "1π subtract ⟨a:i b:i⟩→i = a-b\n"
        "1π multiply ⟨a:i b:i⟩→i = a*b\n"
        "1π divide ⟨a:i b:i⟩→f\n"
        "  pre b≠0\n"
        "  body a/b\n"
    )

    mask_app = _stats_ns(benchmark_mask_application_numpy(iters=iters_fast))
    state_t = _stats_ns(benchmark_state_transition(iters=iters_fast))
    refine_c = _stats_ns(benchmark_refinement_compiled(iters=iters_fast))
    refine_i = _stats_ns(benchmark_refinement_inline(iters=iters_fast))
    e2e = _stats_ns(benchmark_end_to_end(tokenizer_path, sample, iters=iters_e2e))

    # Pi 5 projection: multiply each by PI5_PROJECTION_FACTOR, convert ns → μs.
    pi5_us = {
        "mask_application_p95": (mask_app["p95"] * PI5_PROJECTION_FACTOR) / 1000,
        "state_transition_p95": (state_t["p95"] * PI5_PROJECTION_FACTOR) / 1000,
        "refinement_compiled_p95": (refine_c["p95"] * PI5_PROJECTION_FACTOR) / 1000,
        "end_to_end_p95": (e2e["p95"] * PI5_PROJECTION_FACTOR) / 1000,
    }

    target_us = 50.0
    e2e_p95_pi5 = pi5_us["end_to_end_p95"]
    if e2e_p95_pi5 < target_us:
        verdict = (
            f"PASS: end-to-end p95 projected to {e2e_p95_pi5:.2f}μs on Pi 5, "
            f"under the {target_us}μs/token §1 budget."
        )
    elif e2e_p95_pi5 < target_us * 2:
        verdict = (
            f"REFINE: end-to-end p95 projected to {e2e_p95_pi5:.2f}μs on Pi 5, "
            f"within 2× of the {target_us}μs/token §1 budget — borderline; "
            f"consider three-tier verifier fallback per REFINED_DESIGN.md §1."
        )
    else:
        verdict = (
            f"FAIL: end-to-end p95 projected to {e2e_p95_pi5:.2f}μs on Pi 5, "
            f">2× of the {target_us}μs/token §1 budget. The load-bearing "
            f"lemma weakens; per-function VC discharge fallback required."
        )

    return LatencyReport(
        schema_version="atomadic-lang.latency/v0",
        benchmark_iters=iters_fast,
        mask_application_ns=mask_app,
        state_transition_ns=state_t,
        refinement_compiled_ns=refine_c,
        refinement_inline_ns=refine_i,
        end_to_end_ns=e2e,
        pi5_projection_us=pi5_us,
        target_budget_us=target_us,
        verdict=verdict,
    )
