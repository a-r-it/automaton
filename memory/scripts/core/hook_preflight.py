"""Opt-in marker + recursion-guard short-circuit for hook entrypoints.

Used by ``session-start.py``, ``session-end.py`` and ``pre-compact.py``
from inside their ``if __name__ == "__main__":`` guard. The check runs
BEFORE the @cli_main decorator (i.e. before config_factory loads
``WIKI_ROOT``), so installing the plugin is silently inert in projects
that have not opted in to automation.

Why not a ``preflight=`` kwarg on @cli_main? The current preflight
contract returns ``ExitCode.OK`` to proceed and any non-OK to short-
circuit. Hook entrypoints need to short-circuit with ``OK`` (silent
success) when the marker is absent — the contract has no way to express
that today. Putting the check in the ``__main__`` guard keeps ``main()``
unconditionally callable from tests while the production wrapper remains
safe on non-opt-in projects.

Tests must call the migrated ``main()`` directly to exercise the body —
the marker check only runs from ``__main__``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from scripts.core.constants import (
    AUTOMATON_MARKER_FILENAME,
    CLAUDE_DIR,
    ENV_CLAUDE_INVOKED_BY,
    ENV_CLAUDE_PROJECT_DIR,
)

__all__ = ("opt_in_or_exit",)


def opt_in_or_exit() -> None:
    """Silently ``sys.exit(0)`` unless the project has opted in.

    Short-circuits in three cases:

    1. ``CLAUDE_INVOKED_BY`` is set — the hook was fired by a child
       Claude Code session spawned from ``flush.py``. Recursing into the
       hook would dirty the daily log and burn tokens.
    2. ``CLAUDE_PROJECT_DIR`` is empty/unset — no project context, hook
       cannot resolve the marker location.
    3. ``<CLAUDE_PROJECT_DIR>/.claude/automaton.enabled`` is missing —
       the user has not run ``automaton:wiki setup``.

    Otherwise returns and lets ``main()`` proceed.
    """
    if os.environ.get(ENV_CLAUDE_INVOKED_BY):
        sys.exit(0)
    project_dir = os.environ.get(ENV_CLAUDE_PROJECT_DIR, "").strip()
    if not project_dir:
        sys.exit(0)
    marker = Path(project_dir) / CLAUDE_DIR / AUTOMATON_MARKER_FILENAME
    if not marker.exists():
        sys.exit(0)
