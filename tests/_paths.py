"""Single source of truth for test fixture paths.

The in-repo `tests/fixtures/calc/` package is a tier-organized minimal Python
package used by the `forge lower` / `raise` / `roundtrip` / tokenizer tests.
Shipping it inside the repository makes the test suite self-contained — no
external sibling repo needed for CI, contributors, or MCP clients.

The external `FORGE_ROOT` is still referenced by hold-out density tests
(those are deliberately xfail / skip when the larger Forge corpus is absent).
"""

from __future__ import annotations

from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
TESTS_DIR: Path = _THIS_FILE.parent
PROJECT_ROOT: Path = TESTS_DIR.parent

# In-repo, always present.
CALC_ROOT: Path = TESTS_DIR / "fixtures" / "calc"


def _resolve_forge_root() -> Path:
    """Prefer atomadic-forge-deluxe (canonical), fall back to legacy atomadic-forge.

    Both paths host a tier-organized package usable as a heterogeneous
    hold-out corpus. Hold-out tests are xfail-decorated and skip cleanly
    when neither is present.
    """
    workspace = PROJECT_ROOT.parent
    candidates = (
        workspace / "atomadic-forge-deluxe" / "src" / "atomadic_forge_deluxe",
        workspace / "atomadic-forge" / "src" / "atomadic_forge",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Return the canonical-but-absent path so tests can still skipif on it.
    return candidates[0]


FORGE_ROOT: Path = _resolve_forge_root()
