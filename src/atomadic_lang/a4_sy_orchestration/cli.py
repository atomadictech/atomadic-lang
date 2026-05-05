"""Tier a4 — CLI entry for atomadic-lang.

Subcommands:
  lower    — decompile a tier-organized Python package to .atm

This is the v0 user-facing surface. Mirrors Forge's `forge` Typer app.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from ..a1_at_functions.atm_emit import emit_module
from ..a3_og_features.latency_feature import run_full_benchmark
from ..a3_og_features.lower_feature import lower_package
from ..a3_og_features.raise_feature import raise_atm_file, roundtrip_atm_file
from ..a3_og_features.tokenize_feature import measure_density, train_atm_tokenizer
from ..a1_at_functions.wgrammar_enforce import DEFAULT_OVERFIT_THRESHOLD
from ..a3_og_features.wgrammar_feature import (
    audit_tokenizer_file,
    enforce_tokenizer_file,
    summarise_audit,
)

app = typer.Typer(
    name="atomadic-lang",
    help="Atomadic Lang (.atm) — tier-typed dense language for AI authors.",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Atomadic Lang root — subcommands: lower, raise, roundtrip, tokenize, density, benchmark, wgrammar-audit, version."""
    # Windows consoles default to cp1252 which can't encode Unicode sigils
    # (π, ⟨, →, ▷). Force UTF-8 on stdout for portable terminal output.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    return


@app.command()
def version() -> None:
    """Print the package version and exit."""
    from .. import __version__
    typer.echo(f"atomadic-lang {__version__}")


@app.command()
def tokenize(
    source: list[Path] = typer.Argument(
        ..., help="One or more package roots (or parent dirs containing aN_* subdirs)."
    ),
    output: Path = typer.Option(
        Path("tokenizer.json"), "--output", "-o", help="Where to write the trained tokenizer JSON."
    ),
    corpus_dump: Path | None = typer.Option(
        None, "--corpus-dump", help="Optional path to also write the raw .atm corpus."
    ),
    strict: bool = typer.Option(
        False, "--strict",
        help="v2.9: also drop decls whose rendered body contains ⟪ (raw-Python embedded fallback). "
             "Yields a cleaner BPE training corpus by removing structural-fallback leak.",
    ),
) -> None:
    """Lower the given Python sources, collect a `.atm` corpus, train a BPE."""
    report = train_atm_tokenizer(
        source_roots=list(source),
        output_tokenizer_path=output,
        corpus_dump_path=corpus_dump,
        drop_embedded_structural=strict,
    )
    print(json.dumps(report, indent=2))


@app.command()
def density(
    py_source: Path = typer.Argument(..., help="Path to a Python source file."),
    atm_source: Path = typer.Argument(..., help="Path to the lowered .atm file."),
    tokenizer: Path = typer.Option(
        Path("tokenizer.json"), "--tokenizer", "-t", help="Path to the trained .atm BPE tokenizer."
    ),
) -> None:
    """Measure density: Python tokens (cl100k_base) vs .atm tokens (our BPE)."""
    report = measure_density(
        py_source_path=py_source,
        atm_source_path=atm_source,
        atm_tokenizer_path=tokenizer,
    )
    print(json.dumps(report, indent=2))


@app.command(name="raise")
def raise_cmd(
    atm_source: Path = typer.Argument(..., help="Path to a `.atm` file to parse."),
    json_meta: bool = typer.Option(
        False, "--json", help="Emit the parsed module as JSON to stdout."
    ),
) -> None:
    """Parse .atm source back to a LoweredDecl[] (the inverse of `lower`)."""
    module = raise_atm_file(atm_source)
    if json_meta:
        print(json.dumps(module, indent=2, ensure_ascii=False))
    else:
        print(f"package: {module['package']}")
        print(f"decls: {len(module['decls'])}")
        for d in module["decls"]:
            tier_eff = f"{d['tier']}{d['effect']}"
            print(f"  {tier_eff} {d['name']} ({d['body_form']})")


@app.command()
def roundtrip(
    atm_source: Path = typer.Argument(..., help="Path to a `.atm` file to round-trip."),
) -> None:
    """Round-trip check: parse + re-emit and compare to the original text."""
    report = roundtrip_atm_file(atm_source)
    print(json.dumps(report, indent=2, ensure_ascii=False))


@app.command(name="wgrammar-audit")
def wgrammar_audit_cmd(
    tokenizer: Path = typer.Argument(
        ..., help="Path to a trained .atm BPE tokenizer JSON.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the report as JSON instead of a text summary.",
    ),
    role_listing: bool = typer.Option(
        False, "--role-listing", help="Embed full per-role token listings (large output).",
    ),
    enforce: bool = typer.Option(
        False, "--enforce",
        help="Also enforce an anchored overfit bound. Exit nonzero if "
             "overfit_fraction exceeds the threshold.",
    ),
    max_overfit: float = typer.Option(
        DEFAULT_OVERFIT_THRESHOLD, "--max-overfit",
        help="Max acceptable overfit_fraction in (0, 1]. Defaults to the "
             "anchored OVERFIT_BOUND_DEFAULT = 1 - 1820/1823 = 3/1823.",
    ),
) -> None:
    """W-grammar audit: classify every BPE merge as structural or overfit.

    The overfit fraction is the load-bearing predictor of how well density
    will hold on held-out corpora.

    With ``--enforce``, the command exits nonzero when overfit_fraction
    exceeds ``--max-overfit`` (default: anchored OVERFIT_BOUND_DEFAULT).
    Use this in CI to block tokenizers that won't generalise.
    """
    if enforce:
        report = enforce_tokenizer_file(
            Path(tokenizer),
            threshold=max_overfit,
            include_role_listing=role_listing,
        )
    else:
        report = audit_tokenizer_file(
            Path(tokenizer), include_role_listing=role_listing,
        )
    if json_out:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(summarise_audit(report))
    if enforce and report["enforce"]["verdict"] == "REJECT":
        raise typer.Exit(code=1)


@app.command()
def benchmark(
    tokenizer: Path = typer.Option(
        Path("tokenizer_v15.json"), "--tokenizer", "-t",
        help="Path to a trained .atm BPE tokenizer.",
    ),
    iters_fast: int = typer.Option(100_000, help="Iterations for fast benchmarks."),
    iters_e2e: int = typer.Option(100, help="Iterations for end-to-end benchmark."),
) -> None:
    """Run the v2.0 §1 latency benchmark and report results in JSON."""
    report = run_full_benchmark(
        tokenizer_path=tokenizer,
        iters_fast=iters_fast,
        iters_e2e=iters_e2e,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


@app.command()
def lower(
    package_root: Path = typer.Argument(
        ..., help="Path to the tier-organized package root (the dir that contains aN_* dirs)."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the .atm to this file (default: stdout)."
    ),
    json_meta: bool = typer.Option(
        False, "--json", help="Emit JSON metadata (density, decl count) to stderr."
    ),
) -> None:
    """Lower a Forge-organized Python package to .atm source.

    Example:
      atomadic-lang lower path/to/forge-demo-calc/src/calc -o calc.atm
    """
    module = lower_package(package_root)
    text = emit_module(module["package"], module["decls"])

    if output is not None:
        output.write_text(text, encoding="utf-8")
    else:
        # Windows consoles default to cp1252 which can't encode Unicode sigils
        # (π, ⟨, →, ▷). Force UTF-8 on stdout for portable terminal output.
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            sys.stdout.write(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(text.encode("utf-8"))

    if json_meta:
        meta = {
            "schema_version": module["schema_version"],
            "package": module["package"],
            "decl_count": len(module["decls"]),
            "py_tokens": module["py_token_count"],
            "atm_tokens": module["atm_token_count"],
            "density_ratio": round(module["density_ratio"], 2),
        }
        print(json.dumps(meta), file=sys.stderr)


if __name__ == "__main__":
    app()
