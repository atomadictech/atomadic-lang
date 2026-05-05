#!/usr/bin/env python3
"""Portfolio merge-audit primitive.

Mirrors N tier-organized Python packages (with per-source prefix rename) into
a temporary scratch directory, then runs `forge` and `atomadic-lang`
diagnostics across the merged super-package. Emits a unified JSON report.

Use as a recurring health check across the Atomadic portfolio. Surfaces:

  - inherited architectural violations (e.g. F0042 upward imports)
  - cross-domain emergent compositions (`forge emergent-scan`)
  - tokenizer overfit on a heterogeneous corpus (`atomadic-lang wgrammar-audit`)
  - bugs in the analyzers themselves (`forge dedup` crashes were found this way)

The scratch dir is built fresh each run; canonical source repos are read-only.
By default the scratch dir is removed at exit; pass --keep to retain it for
follow-up inspection.

Usage:

    # use the bundled default config (5-package portfolio merge)
    python tools/merge_audit.py

    # custom config
    python tools/merge_audit.py --config tools/merge_audit.config.json

    # keep the scratch dir for inspection
    python tools/merge_audit.py --keep

    # write report to a file (default: stdout)
    python tools/merge_audit.py --report /tmp/audit.json

Exit codes:
    0   all gates PASS
    1   at least one gate FAIL or REJECT
    2   unexpected error (script bug or missing tool)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


# Default portfolio config — mirrors the V3_EMPIRICAL_FINDING stress test.
DEFAULT_CONFIG: dict[str, Any] = {
    "sources": [
        {"prefix": "frg",  "path": r"C:\!!AtomadicStandard\atomadic-forge\src\atomadic_forge"},
        {"prefix": "dlx",  "path": r"C:\!!AtomadicStandard\atomadic-forge-deluxe\src\atomadic_forge_deluxe"},
        {"prefix": "seed", "path": r"C:\!!AtomadicStandard\forge-deluxe-seed\src\forge_deluxe_seed"},
        {"prefix": "lng",  "path": r"C:\!!AtomadicStandard\atomadic-lang\src\atomadic_lang"},
    ],
    "merged_package_name": "atomadic_omega",
    "tier_dirs": [
        "a0_qk_constants",
        "a1_at_functions",
        "a2_mo_composites",
        "a3_og_features",
        "a4_sy_orchestration",
    ],
}


TIER_DIRS = (
    "a0_qk_constants",
    "a1_at_functions",
    "a2_mo_composites",
    "a3_og_features",
    "a4_sy_orchestration",
)


def _log(msg: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(f"[merge-audit] {msg}", file=sys.stderr, flush=True)


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 600) -> tuple[int, str, str]:
    """Run a subprocess, returning (returncode, stdout, stderr)."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def build_merged_package(
    sources: list[dict[str, str]],
    scratch: Path,
    package_name: str,
    *,
    quiet: bool = False,
) -> dict[str, Any]:
    """Mirror N source packages into scratch/src/<package_name>/ with prefix rename."""
    pkg_root = scratch / "src" / package_name
    for tier in TIER_DIRS:
        (pkg_root / tier).mkdir(parents=True, exist_ok=True)
        (pkg_root / tier / "__init__.py").write_text(
            '"""Tier merged from multiple source packages."""\n', encoding="utf-8"
        )
    pkg_root.joinpath("__init__.py").write_text(
        '"""Merged super-package — see scratch/README.md."""\n', encoding="utf-8"
    )

    counts: dict[str, dict[str, int]] = {}
    total = 0
    for src_entry in sources:
        prefix = src_entry["prefix"]
        src_root = Path(src_entry["path"])
        if not src_root.is_dir():
            _log(f"  source not found, skipping: {src_root}", quiet=quiet)
            continue
        sub_counts: dict[str, int] = {}
        for tier in TIER_DIRS:
            tier_src = src_root / tier
            if not tier_src.is_dir():
                continue
            n = 0
            for f in sorted(tier_src.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                shutil.copy2(f, pkg_root / tier / f"{prefix}_{f.name}")
                n += 1
            sub_counts[tier] = n
            total += n
        counts[prefix] = sub_counts
        _log(f"  merged {prefix}: {sum(sub_counts.values())} files", quiet=quiet)

    # Minimal pyproject + README so forge has a project root to scan.
    scratch.joinpath("pyproject.toml").write_text(
        f"""[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name.replace('_', '-')}"
version = "0.0.1-merge-audit"
description = "Synthetic merge produced by tools/merge_audit.py."
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
        encoding="utf-8",
    )
    scratch.joinpath("README.md").write_text(
        f"# {package_name}\n\nSynthetic merge for stress-testing forge / atomadic-lang.\n",
        encoding="utf-8",
    )

    return {
        "schema_version": "atomadic-lang.merge_audit.merge/v1",
        "scratch_dir": str(scratch),
        "package_root": str(pkg_root),
        "package_name": package_name,
        "per_source_counts": counts,
        "total_files_merged": total,
    }


def run_forge_diagnostics(scratch: Path, *, quiet: bool = False) -> dict[str, Any]:
    """Run forge recon / wire / certify against the merged scratch dir."""
    out: dict[str, Any] = {"schema_version": "atomadic-lang.merge_audit.forge/v1"}

    # `forge recon` — symbol/tier classification
    rc, stdout, stderr = _run(["forge", "recon", str(scratch), "--json"])
    out["recon"] = {
        "exit_code": rc,
        "report": _safe_json(stdout),
        "stderr_excerpt": stderr[:500] if stderr else "",
    }
    _log(f"  forge recon: exit={rc}", quiet=quiet)

    # `forge wire` — upward-import check
    rc, stdout, stderr = _run(
        ["forge", "wire", str(scratch / "src"), "--json"],
    )
    out["wire"] = {
        "exit_code": rc,
        "report": _safe_json(stdout),
        "stderr_excerpt": stderr[:500] if stderr else "",
    }
    _log(f"  forge wire: exit={rc}", quiet=quiet)

    # `forge certify` — full certify roll-up
    rc, stdout, stderr = _run(
        ["forge", "certify", str(scratch), "--json", "--fail-under", "0"],
    )
    out["certify"] = {
        "exit_code": rc,
        "report": _safe_json(stdout),
        "stderr_excerpt": stderr[:500] if stderr else "",
    }
    _log(f"  forge certify: exit={rc}", quiet=quiet)

    return out


def run_lang_diagnostics(
    scratch: Path,
    package_name: str,
    *,
    quiet: bool = False,
) -> dict[str, Any]:
    """Train BPE on the merged package and run wgrammar-audit --enforce."""
    out: dict[str, Any] = {"schema_version": "atomadic-lang.merge_audit.lang/v1"}
    pkg_root = scratch / "src" / package_name
    tok_path = scratch / "tokenizer_merge_audit.json"

    rc, stdout, stderr = _run(
        [
            sys.executable, "-m", "atomadic_lang", "tokenize",
            str(pkg_root),
            "-o", str(tok_path),
            "--strict",
        ],
    )
    out["tokenize"] = {
        "exit_code": rc,
        "report": _safe_json(stdout),
        "stderr_excerpt": stderr[:500] if stderr else "",
        "tokenizer_path": str(tok_path) if tok_path.exists() else "",
    }
    _log(f"  atomadic-lang tokenize: exit={rc}", quiet=quiet)

    if not tok_path.exists():
        out["wgrammar_audit_enforce"] = {
            "exit_code": -1,
            "skipped_because": "tokenizer not produced",
        }
        return out

    rc, stdout, stderr = _run(
        [
            sys.executable, "-m", "atomadic_lang", "wgrammar-audit",
            str(tok_path), "--enforce", "--json",
        ],
    )
    out["wgrammar_audit_enforce"] = {
        "exit_code": rc,
        "report": _safe_json(stdout),
        "stderr_excerpt": stderr[:500] if stderr else "",
    }
    _log(f"  atomadic-lang wgrammar-audit --enforce: exit={rc}", quiet=quiet)

    return out


def _safe_json(text: str) -> Any:
    """Parse text as JSON, returning a string fallback on error."""
    try:
        return json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return text[:2000] if text else ""


def overall_verdict(forge: dict[str, Any], lang: dict[str, Any]) -> str:
    """Compute a single PASS/REFINE/FAIL verdict from the constituent reports."""
    # Any non-zero exit code from a real tool counts.
    forge_exits = [
        forge.get(k, {}).get("exit_code", 0)
        for k in ("recon", "wire", "certify")
    ]
    lang_exits = [
        lang.get(k, {}).get("exit_code", 0)
        for k in ("tokenize", "wgrammar_audit_enforce")
    ]
    if any(e != 0 for e in forge_exits + lang_exits):
        return "FAIL"

    # Look at the certify report verdict if present.
    certify = forge.get("certify", {}).get("report") or {}
    if isinstance(certify, dict):
        verdict = certify.get("_summary", {}).get("verdict") or certify.get("verdict")
        if verdict in ("FAIL", "REJECT"):
            return verdict
        if verdict == "REFINE":
            return "REFINE"

    # Look at the wgrammar enforce verdict.
    enforce = lang.get("wgrammar_audit_enforce", {}).get("report") or {}
    if isinstance(enforce, dict):
        en = enforce.get("enforce", {})
        if en.get("verdict") == "REJECT":
            return "REJECT"

    return "PASS"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument(
        "--config", type=Path, default=None,
        help="Path to a JSON config; defaults to the bundled portfolio config.",
    )
    p.add_argument(
        "--scratch", type=Path, default=None,
        help="Custom scratch dir (default: a fresh tempdir).",
    )
    p.add_argument(
        "--report", type=Path, default=None,
        help="Where to write the unified JSON report (default: stdout).",
    )
    p.add_argument(
        "--keep", action="store_true",
        help="Keep the scratch dir at exit (default: remove).",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress messages on stderr.",
    )
    args = p.parse_args(argv)

    config = (
        json.loads(args.config.read_text(encoding="utf-8"))
        if args.config else DEFAULT_CONFIG
    )

    if args.scratch:
        scratch = args.scratch
        scratch.mkdir(parents=True, exist_ok=True)
        cleanup_scratch = False  # caller owns it
    else:
        scratch = Path(tempfile.mkdtemp(prefix="atomadic-merge-audit-"))
        cleanup_scratch = not args.keep

    started_at = time.time()
    _log(f"scratch dir: {scratch}", quiet=args.quiet)

    try:
        merge_report = build_merged_package(
            config["sources"],
            scratch,
            config["merged_package_name"],
            quiet=args.quiet,
        )
        forge_report = run_forge_diagnostics(scratch, quiet=args.quiet)
        lang_report = run_lang_diagnostics(
            scratch, config["merged_package_name"], quiet=args.quiet
        )
        verdict = overall_verdict(forge_report, lang_report)

        unified: dict[str, Any] = {
            "schema_version": "atomadic-lang.merge_audit/v1",
            "started_at_unix": started_at,
            "duration_seconds": round(time.time() - started_at, 3),
            "verdict": verdict,
            "merge": merge_report,
            "forge": forge_report,
            "lang": lang_report,
            "config_used": config,
        }

        out_text = json.dumps(unified, indent=2, ensure_ascii=False)
        if args.report:
            args.report.write_text(out_text, encoding="utf-8")
            _log(f"report written: {args.report}", quiet=args.quiet)
        else:
            print(out_text)

        return 0 if verdict == "PASS" else 1
    except Exception as exc:  # pragma: no cover — top-level safety net
        print(
            json.dumps({"schema_version": "atomadic-lang.merge_audit/v1",
                        "verdict": "ERROR", "error": repr(exc)}),
            file=sys.stderr,
        )
        return 2
    finally:
        if cleanup_scratch and scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
            _log("scratch dir removed", quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
