"""Tier a2 — stateful corpus accumulator for BPE training.

Accumulates `LoweredDecl` records (rendered to one line each) and
exposes the resulting corpus for downstream BPE training.

a2 imports a0 + a1 only. Package-walking + lowering live in a3.
"""

from __future__ import annotations

from pathlib import Path

from ..a0_qk_constants.atm_types import LoweredDecl
from ..a1_at_functions.atm_emit import emit_decl


class CorpusCollector:
    """Accumulate `.atm` source lines for BPE training.

    Pure stateful container — feed it `LoweredDecl` records and it
    produces a corpus of one-line declarations. Drops structural-fallback
    decls by default (those still contain raw Python and would teach
    the BPE Python merges, which is not what we want).
    """

    def __init__(
        self,
        *,
        drop_structural: bool = True,
        drop_embedded_structural: bool = False,
    ) -> None:
        """Construct a corpus collector.

        Args:
          drop_structural: drop decls whose ``body_form == "structural"``
            (the ``⟪…⟫`` raw-Python fallback). Default True since v0.5.
          drop_embedded_structural (v2.9): drop decls whose **rendered body
            contains** a ``⟪`` brace, even if the decl itself is not a
            structural fallback. This catches tier-0 const decls like
            ``0 DEFAULT_CONFIG : _ = ⟪{...Python dict...}⟫`` whose
            outer body is an expression but inner content is raw Python.
            v2.9 default is False to preserve backward compatibility;
            recommended True for clean BPE training corpora.
        """
        self._lines: list[str] = []
        self._sources: list[str] = []
        self._drop_structural: bool = drop_structural
        self._drop_embedded_structural: bool = drop_embedded_structural
        self._stats: dict[str, int] = {
            "packages_added": 0,
            "decls_collected": 0,
            "decls_dropped_structural": 0,
            "decls_dropped_embedded": 0,
            "total_atm_chars": 0,
        }

    def add_decls(self, decls: list[LoweredDecl], *, package_count_increment: int = 1) -> int:
        """Append a batch of lowered declarations to the corpus.

        `package_count_increment` should be 1 when the batch represents
        a single package; pass 0 if you're feeding decls from many sources
        and tracking package count externally.
        Returns the number of decls actually appended (after structural-drop).
        """
        added = 0
        for decl in decls:
            line = self._render_decl_line(decl)
            if line is None:
                continue
            self._lines.append(line)
            self._sources.append(decl["source_path"])
            self._stats["total_atm_chars"] += len(line)
            added += 1
        if added > 0:
            self._stats["packages_added"] += package_count_increment
            self._stats["decls_collected"] += added
        return added

    def lines(self) -> list[str]:
        """Return the collected corpus lines (one decl per line)."""
        return list(self._lines)

    def joined(self) -> str:
        """Return the corpus as a single newline-joined string."""
        return "\n".join(self._lines) + ("\n" if self._lines else "")

    def stats(self) -> dict[str, int]:
        """Return collection statistics for audit / lineage."""
        return dict(self._stats)

    def write(self, out_path: Path) -> None:
        """Persist the corpus to a UTF-8 text file."""
        Path(out_path).write_text(self.joined(), encoding="utf-8")

    def _render_decl_line(self, decl: LoweredDecl) -> str | None:
        if self._drop_structural and decl["body_form"] == "structural":
            self._stats["decls_dropped_structural"] += 1
            return None
        rendered = emit_decl(decl)
        # Fold multi-line refinement blocks to one line for streaming-friendly corpus.
        line = " ; ".join(s.strip() for s in rendered.splitlines() if s.strip())
        # v2.9 — drop decls with embedded structural fallbacks (raw Python
        # inside ⟪…⟫). The opening brace ⟪ (U+27EA) is the signal: if
        # present, the BPE will learn whatever Python detritus the inner
        # content contains, which is the v2.7/v2.8 overfit source.
        if self._drop_embedded_structural and "⟪" in line:
            self._stats["decls_dropped_embedded"] += 1
            return None
        return line
