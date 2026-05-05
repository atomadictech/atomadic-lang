"""Tier a3 — orchestrate `.atm → LoweredDecl[]` parsing and round-trip checks.

`forge raise` is the inverse of `forge lower`. Round-trip property:

    lower(py) → emit_module → parse_module → emit_module == original_emit

When this property holds, the surface grammar is round-trippable on the
sample. v1.0 verifies it on calc + atomadic_forge.

Imports a0, a1.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from ..a0_qk_constants.atm_types import LoweredDecl, LoweredModule
from ..a1_at_functions.atm_emit import emit_module
from ..a1_at_functions.atm_parse import parse_module


def raise_atm_text(atm_text: str) -> LoweredModule:
    """Parse `.atm` source text into a LoweredModule (alias of parse_module)."""
    return parse_module(atm_text)


def raise_atm_file(atm_path: Path) -> LoweredModule:
    """Parse a `.atm` file from disk into a LoweredModule."""
    return parse_module(Path(atm_path).read_text(encoding="utf-8"))


class RoundtripReport(TypedDict):
    schema_version: str
    file_path: str
    original_decl_count: int
    raised_decl_count: int
    decl_count_match: bool
    text_identical: bool
    diff_first_chars: int      # chars where the two emissions first differ; -1 if identical
    sample_diff: str           # short window around first difference (or "")


def roundtrip_atm_file(atm_path: Path) -> RoundtripReport:
    """Round-trip check: read .atm, parse, re-emit, compare to original.

    Returns a structured report (no exceptions on mismatch — the diff is
    inspectable via the report fields).
    """
    original = Path(atm_path).read_text(encoding="utf-8")
    parsed = parse_module(original)
    re_emitted = emit_module(parsed["package"], parsed["decls"])
    return _diff_report(
        file_path=str(Path(atm_path).resolve()),
        original=original,
        re_emitted=re_emitted,
        parsed_decls=len(parsed["decls"]),
    )


def roundtrip_decls(decls: list[LoweredDecl], package: str) -> RoundtripReport:
    """In-memory round-trip: emit, parse, re-emit, compare.

    Used by tests where the input is already a list of LoweredDecl.
    """
    original = emit_module(package, decls)
    parsed = parse_module(original)
    re_emitted = emit_module(parsed["package"], parsed["decls"])
    return _diff_report(
        file_path="<in-memory>",
        original=original,
        re_emitted=re_emitted,
        parsed_decls=len(parsed["decls"]),
        original_decls=len(decls),
    )


def _diff_report(
    *,
    file_path: str,
    original: str,
    re_emitted: str,
    parsed_decls: int,
    original_decls: int | None = None,
) -> RoundtripReport:
    if original == re_emitted:
        return RoundtripReport(
            schema_version="atomadic-lang.roundtrip/v0",
            file_path=file_path,
            original_decl_count=original_decls if original_decls is not None else parsed_decls,
            raised_decl_count=parsed_decls,
            decl_count_match=(original_decls is None or original_decls == parsed_decls),
            text_identical=True,
            diff_first_chars=-1,
            sample_diff="",
        )

    # Find first divergence point.
    n = min(len(original), len(re_emitted))
    first = next((i for i in range(n) if original[i] != re_emitted[i]), n)
    window = 80
    a = original[max(0, first - window) : first + window]
    b = re_emitted[max(0, first - window) : first + window]
    sample = (
        f"...orig...\n{a}\n...vs raised...\n{b}"
    )

    return RoundtripReport(
        schema_version="atomadic-lang.roundtrip/v0",
        file_path=file_path,
        original_decl_count=original_decls if original_decls is not None else parsed_decls,
        raised_decl_count=parsed_decls,
        decl_count_match=(original_decls is None or original_decls == parsed_decls),
        text_identical=False,
        diff_first_chars=first,
        sample_diff=sample,
    )
