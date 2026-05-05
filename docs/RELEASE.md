# Release Runbook

This repo ships the `.atm` toolchain. The MCP server surface is provided by
Atomadic Forge through `forge mcp serve`; keep both releases aligned because
`atomadic-lang` is one of the primary repositories the Forge MCP should be able
to inspect, wire, and certify.

## Local Release Gate

Run these from the repository root before tagging:

```bash
python -m ruff check .
python -m pytest
python -m build --sdist --wheel
python -m atomadic_lang roundtrip calc.atm
forge wire src/atomadic_lang --fail-on-violations
forge certify . --package atomadic_lang --fail-under 70
```

On Windows, if `python -m build` completes package creation but fails while
deleting its temporary isolated environment with `WinError 32`, rerun:

```bash
python -m build --no-isolation --sdist --wheel
```

Use the isolated build in CI and for final publishing whenever the host allows
the temporary environment to clean up normally.

Expected state as of this release-hardening pass:

- Ruff passes.
- Pytest reports `208 passed, 2 xfailed`.
- Package build creates an sdist and wheel with `atomadic_lang/py.typed`.
- `calc.atm` round-trips byte-identically.
- Forge wire verdict is `PASS`.
- Forge certify score is `70.0` with no issues or recommendations.

## Version And Changelog

1. Update `version` in `pyproject.toml`.
2. Update `__version__` in `src/atomadic_lang/__init__.py`.
3. Move relevant `CHANGELOG.md` entries from `[Unreleased]` into the new
   version section with the release date.
4. Re-run the local release gate.

## MCP Release Gate

The Forge MCP command is:

```bash
forge mcp serve --project /path/to/atomadic-lang
```

Client configuration shape:

```json
{
  "mcpServers": {
    "atomadic-forge": {
      "command": "forge",
      "args": ["mcp", "serve", "--project", "/path/to/atomadic-lang"]
    }
  }
}
```

Before publishing the MCP package/registry entry, confirm with `tools/list`
and `resources/list` from a real MCP client:

- It lists the intended tools:
  `recon`, `wire`, `certify`, `enforce`, `audit_list`, `auto_plan`.
- It lists the intended resources:
  `forge://docs/receipt`, `forge://docs/formalization`,
  `forge://lineage/chain`, `forge://schema/receipt`,
  `forge://summary/blockers`.
- `auto_plan` returns an `atomadic-forge.agent_plan/v1` payload with a compact
  `_summary` alongside the full plan.
- `forge://summary/blockers` returns a single compact blocker summary for this
  repository.
- Each tool works against this repo through the MCP client you plan to support.
- Tool descriptions make the operating project explicit so hosts do not confuse
  multiple local repositories.
- The registry/package metadata points users to the same command and arguments
  shown above.

## Publish Notes

- `atomadic-forge` is currently installed locally from a sibling editable
  checkout in this workspace; it was not discoverable from PyPI during this
  pass. Keep CI Forge checks optional until Forge is published or otherwise
  installable in CI.
- The MCP Registry expects package validation metadata for published servers.
  Check the current registry quickstart immediately before publication because
  the registry schema is still evolving.
