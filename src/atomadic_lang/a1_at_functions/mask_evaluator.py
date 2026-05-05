"""Tier a1 — pure mask evaluator for the v2.0 §1 latency benchmark.

Given a parser-state and the v1.5 BPE vocabulary, returns a bitmap of
tokens legal at the current position. Designed for the constrained-decoding
path: at every emitted token the model's logits are masked by this bitmap
before softmax.

This implementation is the v2.0 measurement substrate. It is NOT integrated
with llguidance / XGrammar — that's a v2.5+ deliverable. v2.0 only needs to
answer: *can we compute the mask in <50μs?*

Imports a0 only.
"""

from __future__ import annotations

from typing import Callable

from ..a0_qk_constants.bpe_config import VOCAB_SIZE
from ..a0_qk_constants.grammar_states import (
    ARROW_OR_BODY,
    DECL_NAME,
    DECL_START,
    EQUALS_OR_REFINEMENT,
    INLINE_BODY,
    MODULE_START,
    PARAM_COLON,
    PARAM_NAME,
    PARAM_SEP_OR_CLOSE,
    PARAM_TYPE,
    PARAMS_OPEN,
    REFINEMENT_CLAUSE,
    RETURN_TYPE,
)


# A mask is a bytes object of VOCAB_SIZE / 8 bytes = 512 bytes.
# This makes mask construction + masking memory-bandwidth bound.
MASK_BYTES: int = VOCAB_SIZE // 8


def empty_mask() -> bytearray:
    """Return a fresh all-zero mask (no tokens permitted)."""
    return bytearray(MASK_BYTES)


def all_mask() -> bytearray:
    """Return a fresh all-ones mask (every token permitted)."""
    return bytearray(b"\xff" * MASK_BYTES)


def set_token(mask: bytearray, token_id: int) -> None:
    """Mark `token_id` as permitted in the mask."""
    mask[token_id >> 3] |= 1 << (token_id & 7)


def is_permitted(mask: bytes, token_id: int) -> bool:
    """Check whether `token_id` is permitted in the mask."""
    return bool(mask[token_id >> 3] & (1 << (token_id & 7)))


def precompute_phase_masks(
    vocab: dict[str, int],
) -> dict[str, bytes]:
    """Precompute one bitmap per grammar phase.

    The contract: in phase X, the only permitted tokens are those whose
    string representation is consistent with the v0..v0.9 surface grammar
    at that position. Returns a dict from phase name → bitmap.

    Build cost: O(|vocab| * |phases|) = ~50k ops, runs once at startup.
    Lookup cost at decode time: O(1) — just hand back the precomputed mask.
    """
    masks: dict[str, bytearray] = {phase: empty_mask() for phase in (
        MODULE_START, DECL_START, DECL_NAME, PARAMS_OPEN, PARAM_NAME,
        PARAM_COLON, PARAM_TYPE, PARAM_SEP_OR_CLOSE, ARROW_OR_BODY,
        RETURN_TYPE, EQUALS_OR_REFINEMENT, INLINE_BODY, REFINEMENT_CLAUSE,
    )}

    for tok, tid in vocab.items():
        # MODULE_START: only `@`-prefixed tokens or whitespace.
        if tok.startswith("@") or tok in ("\n", " "):
            set_token(masks[MODULE_START], tid)
        # DECL_START: tier digit, possibly with effect sigil glued (e.g. `1π`).
        if tok and tok[0] in "01234":
            set_token(masks[DECL_START], tid)
        # DECL_NAME: identifier-like (name or dotted name).
        if tok and (tok[0].isalpha() or tok[0] == "_"):
            set_token(masks[DECL_NAME], tid)
        # PARAMS_OPEN: ⟨ or ⟨a:i (forced bigram) or `:` (tier-0) or `=` (no params).
        if tok.startswith("⟨") or tok.startswith(":") or tok == "=":
            set_token(masks[PARAMS_OPEN], tid)
        # PARAM_NAME: identifier inside params.
        if tok and (tok[0].isalpha() or tok[0] == "_") and "=" not in tok:
            set_token(masks[PARAM_NAME], tid)
        # PARAM_COLON: `:` or forced bigrams `:i`/`:s`/etc.
        if tok.startswith(":"):
            set_token(masks[PARAM_COLON], tid)
        # PARAM_TYPE: type sigils i/f/s/b/_/∅ or composite [.../{...}.
        if tok in {"i", "f", "s", "b", "_", "∅"} or tok.startswith(("[", "{", "?", ":[", ":{")):
            set_token(masks[PARAM_TYPE], tid)
        # PARAM_SEP_OR_CLOSE: space, `⟩`, or `⟩→...` forced bigrams.
        if tok == "⟩" or tok.startswith("⟩"):
            set_token(masks[PARAM_SEP_OR_CLOSE], tid)
        # ARROW_OR_BODY: `→`, forced `→i`/`→s`/etc., or end-of-decl whitespace.
        if tok.startswith("→") or tok in ("\n", " "):
            set_token(masks[ARROW_OR_BODY], tid)
        # RETURN_TYPE: type sigil (same set as PARAM_TYPE).
        if tok in {"i", "f", "s", "b", "_", "∅"} or tok.startswith(("[", "{", "?")):
            set_token(masks[RETURN_TYPE], tid)
        # EQUALS_OR_REFINEMENT: `=` or newline.
        if tok == "=" or tok == "\n" or tok == " ":
            set_token(masks[EQUALS_OR_REFINEMENT], tid)
        # INLINE_BODY: free expression — almost any token; mask is mostly all-ones.
        # We mask out only structural keywords that don't make sense in a body.
        if tok not in {"@", "pre", "post"}:
            set_token(masks[INLINE_BODY], tid)
        # REFINEMENT_CLAUSE: keywords `pre`/`post`/`body` start a clause.
        if tok in {"pre", "post", "body"} or tok == " ":
            set_token(masks[REFINEMENT_CLAUSE], tid)

    return {phase: bytes(mask) for phase, mask in masks.items()}


def transition(state: str, token: str, tier_seen: int | None = None) -> str:
    """Advance the grammar state machine given the just-emitted `token`.

    Pure function — no mutation of caller state. Caller threads the new
    state into the next call.
    """
    if state == MODULE_START:
        if token.startswith("@"):
            return DECL_START
        return MODULE_START
    if state == DECL_START:
        if token and token[0] in "01234":
            return DECL_NAME
        return DECL_START
    if state == DECL_NAME:
        if token.startswith("⟨"):
            # v2.6 fix (per swarm code-critic): the previous check `"⟨a" not in token`
            # hardcoded the parameter name `a`. Any token containing "⟨a" (e.g. forced
            # bigrams `⟨a:i`, `⟨a:s`, `⟨a:f`) is the merged form `⟨name:type`. Any
            # token that starts with `⟨` and is longer than 1 char is a merged form
            # too — we transition past PARAM_NAME directly.
            if len(token) > 1:
                return PARAM_TYPE
            return PARAM_NAME
        if token == "=" or token.startswith(":"):
            return INLINE_BODY
        return PARAMS_OPEN
    if state == PARAMS_OPEN:
        if token == "⟨":
            return PARAM_NAME
        if token.startswith("⟨"):
            return PARAM_TYPE
        if token == "=":
            return INLINE_BODY
        return PARAMS_OPEN
    if state == PARAM_NAME:
        if token == ":" or token.startswith(":"):
            return PARAM_TYPE
        return PARAM_NAME
    if state == PARAM_COLON:
        return PARAM_TYPE
    if state == PARAM_TYPE:
        if token == "⟩" or token.startswith("⟩"):
            return ARROW_OR_BODY
        return PARAM_SEP_OR_CLOSE
    if state == PARAM_SEP_OR_CLOSE:
        if token == "⟩" or token.startswith("⟩"):
            return ARROW_OR_BODY
        return PARAM_NAME
    if state == ARROW_OR_BODY:
        if token == "→" or token.startswith("→"):
            return RETURN_TYPE
        return DECL_START  # next decl
    if state == RETURN_TYPE:
        return EQUALS_OR_REFINEMENT
    if state == EQUALS_OR_REFINEMENT:
        if token == "=":
            return INLINE_BODY
        return REFINEMENT_CLAUSE
    if state == INLINE_BODY:
        # v2.6 fix (per swarm code-critic): WhitespaceSplit pre-tokenizer never
        # emits a bare "\n" token, so the previous exit check was unreachable.
        # Detect end-of-decl by either an embedded newline or a token starting
        # with a tier digit (the head of the next decl).
        if "\n" in token or (token and token[0] in "01234"):
            return DECL_START
        return INLINE_BODY
    if state == REFINEMENT_CLAUSE:
        if "\n" in token or (token and token[0] in "01234"):
            return DECL_START
        return REFINEMENT_CLAUSE
    return state


def make_mask_fn(
    phase_masks: dict[str, bytes],
) -> Callable[[str], bytes]:
    """Return a closure that takes a state and returns its precomputed mask."""
    def mask_for(state: str) -> bytes:
        return phase_masks.get(state, b"\xff" * MASK_BYTES)
    return mask_for
