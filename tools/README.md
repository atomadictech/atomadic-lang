# tools/

Repeatable health-check primitives for the Atomadic portfolio.

## `merge_audit.py` — recurring portfolio stress test

Mirrors N tier-organized Python packages into a fresh scratch directory, runs
`forge` and `atomadic-lang` diagnostics against the merged super-package, and
emits a unified JSON report.

This is the automated form of the manual stress test documented in
[`docs/FORGE_DELUXE_EXPERIENCE.md`](../docs/FORGE_DELUXE_EXPERIENCE.md). It
surfaces (a) architectural violations inherited from any source package,
(b) cross-domain emergent compositions, (c) tokenizer overfit on a
heterogeneous corpus, and (d) bugs in the analyzers themselves
(forge-deluxe `dedup` was found to crash on a 821-file corpus this way).

### Quick start

```bash
# default 4-package portfolio config (atomadic-forge, atomadic-forge-deluxe,
# forge-deluxe-seed, atomadic-lang); writes JSON to stdout
python tools/merge_audit.py

# write to a file
python tools/merge_audit.py --report /tmp/audit.json

# keep the scratch dir for inspection (default: remove at exit)
python tools/merge_audit.py --keep --quiet

# use a custom config (see merge_audit.config.example.json)
python tools/merge_audit.py --config tools/merge_audit.config.example.json
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | all gates PASS |
| `1` | at least one gate FAIL or REJECT |
| `2` | unexpected error (script bug or missing tool) |

### What the report contains

```
{
  "schema_version": "atomadic-lang.merge_audit/v1",
  "verdict":        "PASS" | "REFINE" | "FAIL" | "REJECT" | "ERROR",
  "duration_seconds": <float>,
  "merge":  {…per-source file counts, scratch dir, package name…},
  "forge":  {recon: {…}, wire: {…}, certify: {…}},
  "lang":   {tokenize: {…}, wgrammar_audit_enforce: {…}}
}
```

Each tool sub-block carries `exit_code`, the parsed JSON `report`, and a
truncated `stderr_excerpt` for diagnostics.

### Read-only on canonical repos

Source repos are only read. The merged super-package is built in a fresh
tempdir each run and (by default) deleted at exit. Pass `--keep` to retain it
for follow-up inspection.

### When to run

- Before a release of `atomadic-forge` or `atomadic-forge-deluxe` — surfaces
  inherited violations the per-repo gates would miss.
- After a major refactor in any portfolio package — measures whether the
  refactor introduced cross-package drift.
- On a recurring CI cron — turns the stress test into a continuous gate.

### Caveats

- The merged tree is for **static analysis only**, not for runtime use.
  Cross-package imports are intentionally broken by the prefix rename.
- `forge dedup` is currently known to crash on the merged corpus
  (`MCP error -32000` — see `FORGE_DELUXE_EXPERIENCE.md` §1). This script
  does not invoke `dedup` to keep the run reliable. Add it back once the
  upstream fix lands.
- The `atomadic-lang` BPE training step takes 5–15 s on a 5-package corpus
  with ~800 `.py` files. Plan accordingly for CI integration.
