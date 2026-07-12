#!/usr/bin/env python3
"""Deterministic stdlib-only HTML renderer for business-research V2 artifacts.
Contract: docs/research/specs/2026-07-10-business-research-v2-html-design.md §4, §7, §8.

Consumes `business_research.validation.*` directly (via `load_run`) — every
staged artifact is re-validated here (defense in depth: the orchestrator
already validated each on write, this is the renderer's own gate). The LLM
never writes HTML: this
script is the only place business-panel / business-verification /
business-synthesis JSON becomes markup, and every LLM- or web-derived string
goes through `esc`/`safe_url` on the way in.

Every section produces real markup, including the chart/KPI-card layer
(spec §8 items 4-5): `group_charts` groups one panelist's verified data
points into deterministic line/bar SVG charts (chart-compatibility rules,
spec §8 item 5), `render_kpi_strip` shows a capped, deterministically
selected cross-panelist highlight strip of the rest as cards, and each
panelist's own `render_section` shows that panelist's charts plus whatever
of its own cards didn't make the strip — see `_global_kpi_pool` for exactly
how a verified data point ends up in one, and only one, of those three
places.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from business_research.rendering.report import RenderInputError, load_run, render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("build_dir")
    ap.add_argument("out_html")
    args = ap.parse_args(argv)

    try:
        run = load_run(args.build_dir)
    except RenderInputError as e:
        print("\n".join(e.lines))
        return 1

    try:
        # Render fully to a string first (never a partial write): any bug in
        # this module's own rendering logic — as opposed to a bad input
        # artifact, already ruled out by `load_run` above — surfaces here as
        # a named line instead of a raw traceback. Bare `Exception` is a
        # deliberate CLI-boundary safety net (explicit handling: named error
        # printed, exit 1, nothing swallowed), not a substitute for specific
        # `except` clauses inside the module.
        html_text = render(run)
    except Exception as e:  # noqa: BLE001 - last-resort CLI boundary, see comment above
        print(f"E-render-internal: {e}")
        return 1

    out_path = Path(args.out_html)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_text, encoding="utf-8")
    except OSError as e:
        print(f"E-render-output: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
