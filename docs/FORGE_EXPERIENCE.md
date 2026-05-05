# Atomadic Forge (standard) — field report

**Date**: 2026-05-05
**Target**: `atomadic-forge` 0.7.0 — the **flagship product**, exercised
via the CLI (`forge` binary) against the 5-package merged stress corpus
(818 `.py` files, 3,366 classified symbols).

**Companion doc**: [`docs/FORGE_DELUXE_EXPERIENCE.md`](FORGE_DELUXE_EXPERIENCE.md)
— this covers `atomadic-forge-deluxe`, which is currently on the back
burner per user direction. Findings there remain valid; that work
resumes when the deluxe MCP layer is hardened.

This doc covers what the **standard forge CLI** can do today on a
heterogeneous portfolio merge.

## Headline

The standard CLI is solid end-to-end. Every CLI verb tested produces
sensible output on the 818-file merge in under a few seconds. The
"-32000 crash" pattern documented in the deluxe MCP companion doc
**does not affect the standard CLI** — same logic, different transport.

## Surface tested (all `forge <verb>` CLI calls against the merge)

| Verb | Result | Notes |
|---|---|---|
| `forge --version` | `atomadic-forge 0.7.0` | flagship version |
| `forge recon <merge>` | ✅ exit 0 | 822 .py files, 3,366 symbols, full tier+effect distribution |
| `forge wire <merge>/src` | ✅ verdict=PASS, 0 violations | confirms post-enforce state |
| `forge certify <merge> --json` | ✅ exit 0 | full JSON report (CLI-side parser is canonical here) |
| `forge sbom <merge>` | ✅ exit 0 | CycloneDX 1.5, components=0 (no pyproject deps in the synthetic merge) |
| `forge emergent scan --src-root <merge>/src --package atomadic_omega --top-n 3` | ✅ exit 0 | 3 cross-domain pipelines at score 94, all pure, all touching ≥3 domains |
| `forge context-pack <merge>` | ✅ exit 0 | repo purpose + tier map + verdict + best-next-action |
| `forge recipes` | ✅ exit 0 | lists 7 golden-path recipes (`release_hardening`, `add_cli_command`, `fix_wire_violation`, `add_feature`, `bump_version`, `fix_test_detection`, `publish_mcp`) |
| `forge plan <merge>` | ✅ exit 0 | (note: the CLI flag is `--top` not `--top-n` — that's a small CLI/MCP shape divergence worth documenting) |
| `forge preflight <intent> <files...>` | ✅ exit 0 | (positional args, not `--intent` flag) |

## Two top emergent compositions on the merged corpus

`forge emergent scan` (score 94 each) — same shape across the top 3,
all flagged as "domain pair has no existing a3 feature":

```
dlx → frg → seed     all bridges named-typed, pure, novel
dlx → seed → frg     symmetric variant
frg → dlx → seed     symmetric variant
```

These are concrete materialization candidates for the deluxe agent
when their work resumes — each chain has a one-call adapter snippet
in the JSON output.

## CLI vs MCP shape divergences worth noting

A few small flag/option differences between standard CLI and the
deluxe MCP:

- `forge plan` CLI uses `--top` ; deluxe MCP `auto_plan` uses `top_n`
- `forge preflight` CLI takes positional `INTENT FILES...` ; deluxe MCP `preflight_change` uses `intent` + `proposed_files`
- `forge emergent scan` CLI takes `--src-root` + `--package` ; deluxe MCP `emergent_scan` uses `project_root` + `package`

None of these are bugs — they're surface conventions. They do mean
that wrappers / CI scripts written against the CLI will need adapter
shims to talk to the MCP, and vice versa.

## Status

The standard `atomadic-forge` CLI is **the active flagship product**
and is **fully functional** on heterogeneous portfolio corpora at the
818-file scale tested here. The deluxe MCP layer is on the back burner
pending the serialisation-layer fix documented in the companion doc.

For agents picking up forge work in this codebase: prefer the standard
CLI as the canonical entry point. MCP wrappers will remain available
but the CLI is what's recommended until deluxe MCP fixes ship.
