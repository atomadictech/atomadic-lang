"""End-to-end CLI smoke tests (v2.7).

Per swarm code-critic finding: the 110 prior tests are all unit-shaped.
These smoke tests exercise the full CLI pipeline via `subprocess` so the
public command surface stays defensible. Each test verifies one
public subcommand reaches a sensible exit state on a real input.

These tests are deliberately broad (validate exit code + presence of
expected text) rather than narrow (assert exact output) so they don't
break on cosmetic formatting changes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


from tests._paths import CALC_ROOT, PROJECT_ROOT


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m atomadic_lang ...` and capture output."""
    cmd = [sys.executable, "-m", "atomadic_lang", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )


def test_cli_version_returns_clean() -> None:
    result = _run_cli("version")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "atomadic-lang" in result.stdout


def test_cli_help_lists_all_subcommands() -> None:
    result = _run_cli("--help")
    assert result.returncode == 0
    # All 7 v2.5+ subcommands should appear.
    for sub in ("lower", "raise", "roundtrip", "tokenize", "density", "benchmark", "version"):
        assert sub in result.stdout, f"subcommand {sub!r} missing from --help: {result.stdout}"


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_cli_lower_then_roundtrip_on_calc(tmp_path: Path) -> None:
    """Lower the calc demo via CLI, then verify round-trip via CLI."""
    atm_path = tmp_path / "calc.atm"
    lower_result = _run_cli("lower", str(CALC_ROOT), "-o", str(atm_path))
    assert lower_result.returncode == 0, (
        f"lower failed: stderr={lower_result.stderr}"
    )
    assert atm_path.exists()
    text = atm_path.read_text(encoding="utf-8")
    assert text.startswith("@calc")
    assert "1π add" in text

    rt_result = _run_cli("roundtrip", str(atm_path))
    assert rt_result.returncode == 0
    report = json.loads(rt_result.stdout)
    assert report["text_identical"] is True, (
        f"round-trip not identical at char {report['diff_first_chars']}"
    )


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_cli_raise_emits_decl_summary(tmp_path: Path) -> None:
    """Lower then raise — verify the parse summary mentions known decls."""
    atm_path = tmp_path / "calc.atm"
    _run_cli("lower", str(CALC_ROOT), "-o", str(atm_path))
    assert atm_path.exists()
    raise_result = _run_cli("raise", str(atm_path))
    assert raise_result.returncode == 0, f"stderr: {raise_result.stderr}"
    out = raise_result.stdout
    assert "package: calc" in out
    assert "1π add" in out
    assert "1π divide" in out


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_cli_tokenize_then_density(tmp_path: Path) -> None:
    """Train a tokenizer then measure density via CLI."""
    tok_path = tmp_path / "tokenizer.json"
    atm_path = tmp_path / "calc.atm"

    # Lower + tokenize.
    _run_cli("lower", str(CALC_ROOT), "-o", str(atm_path))
    tokenize_result = _run_cli(
        "tokenize", str(CALC_ROOT), "-o", str(tok_path)
    )
    assert tokenize_result.returncode == 0
    assert tok_path.exists()

    # Density check on a single Python file vs the lowered atm.
    add_py = CALC_ROOT / "a1_at_functions" / "add.py"
    density_result = _run_cli(
        "density", str(add_py), str(atm_path), "--tokenizer", str(tok_path)
    )
    assert density_result.returncode == 0, f"stderr: {density_result.stderr}"
    report = json.loads(density_result.stdout)
    assert report["py_token_count"] > 0
    assert report["atm_token_count"] > 0
    assert report["density_ratio"] >= 0.0  # don't pin specific number — varies with calc.atm


@pytest.mark.skipif(not CALC_ROOT.exists(), reason="calc demo not present")
def test_cli_benchmark_runs_to_completion(tmp_path: Path) -> None:
    """Run the §1 latency benchmark via CLI; verify report shape."""
    tok_path = tmp_path / "tokenizer.json"
    _run_cli("tokenize", str(CALC_ROOT), "-o", str(tok_path))
    bench_result = _run_cli(
        "benchmark", "--tokenizer", str(tok_path),
        "--iters-fast", "5000",  # small for test speed
        "--iters-e2e", "10",
    )
    assert bench_result.returncode == 0, f"stderr: {bench_result.stderr}"
    report = json.loads(bench_result.stdout)
    # Required fields present + sensible.
    for key in ("end_to_end_ns", "mask_application_ns", "state_transition_ns",
                "refinement_compiled_ns", "pi5_projection_us", "verdict"):
        assert key in report
    # Verdict is a known prefix (we don't pin PASS/REFINE/FAIL — depends on hardware).
    assert report["verdict"].startswith(("PASS", "REFINE", "FAIL"))


def test_cli_lower_on_nonexistent_path_fails_cleanly(tmp_path: Path) -> None:
    """Negative test: invalid input path should exit nonzero with a sensible error."""
    result = _run_cli("lower", str(tmp_path / "does_not_exist"))
    assert result.returncode != 0
    # Either stderr or stdout should mention the issue
    combined = (result.stderr + result.stdout).lower()
    assert "does not exist" in combined or "error" in combined or "valueerror" in combined


def test_cli_wgrammar_audit_enforce_passes_on_loose_threshold(tmp_path: Path) -> None:
    """--enforce with a loose --max-overfit (1.0) must pass any tokenizer."""
    tok_path = tmp_path / "tokenizer.json"
    _run_cli("tokenize", str(CALC_ROOT), "-o", str(tok_path))
    result = _run_cli(
        "wgrammar-audit", str(tok_path),
        "--enforce", "--max-overfit", "1.0", "--json",
    )
    assert result.returncode == 0, f"loose enforce should pass; stderr: {result.stderr}"
    report = json.loads(result.stdout)
    assert report["enforce"]["verdict"] == "PASS"
    assert report["enforce"]["threshold"] == 1.0
    assert report["enforce"]["threshold_source"] == "override"


def test_cli_wgrammar_audit_enforce_rejects_on_strict_threshold(tmp_path: Path) -> None:
    """--enforce with --max-overfit=0.0 must REJECT any tokenizer with any overfit."""
    tok_path = tmp_path / "tokenizer.json"
    _run_cli("tokenize", str(CALC_ROOT), "-o", str(tok_path))
    # Use a threshold tighter than the default bound so any unknown fraction rejects.
    result = _run_cli(
        "wgrammar-audit", str(tok_path),
        "--enforce", "--max-overfit", "1e-12", "--json",
    )
    # If the trained tokenizer happens to have zero overfit, the test would
    # PASS — but in practice calc-only training yields nonzero unknowns.
    report = json.loads(result.stdout)
    if report["overfit_fraction"] > 1e-12:
        assert result.returncode == 1, (
            f"strict enforce should exit 1; got {result.returncode}"
        )
        assert report["enforce"]["verdict"] == "REJECT"


def test_cli_wgrammar_audit_no_enforce_does_not_exit_nonzero(tmp_path: Path) -> None:
    """Without --enforce, the audit must not affect exit code regardless of overfit."""
    tok_path = tmp_path / "tokenizer.json"
    _run_cli("tokenize", str(CALC_ROOT), "-o", str(tok_path))
    result = _run_cli("wgrammar-audit", str(tok_path), "--json")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert "enforce" not in report  # not present without --enforce


def test_cli_wgrammar_audit_text_mode_renders_enforce_block(tmp_path: Path) -> None:
    """Text mode (no --json) must render the enforce block for human readers."""
    tok_path = tmp_path / "tokenizer.json"
    _run_cli("tokenize", str(CALC_ROOT), "-o", str(tok_path))
    # Loose threshold so we see PASS regardless of corpus.
    result = _run_cli(
        "wgrammar-audit", str(tok_path), "--enforce", "--max-overfit", "1.0",
    )
    assert result.returncode == 0
    assert "enforce:" in result.stdout
    assert "verdict:" in result.stdout
    assert "PASS" in result.stdout or "REJECT" in result.stdout
    assert "threshold:" in result.stdout
    assert "ratio_to_thresh:" in result.stdout
