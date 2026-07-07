"""Opt-in check + recursion-guard short-circuit for hook entrypoints.

Used by session-start, session-end and pre-compact from inside their
``if __name__ == "__main__":`` guard. Runs BEFORE @cli_main so the
plugin is silently inert in projects that have not run setup.

Tests call main() directly — the opt-in check only runs from __main__.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from scripts.core import config_io
from scripts.core.constants import (
    ENV_CLAUDE_INVOKED_BY,
    ENV_CLAUDE_PROJECT_DIR,
)

__all__ = ("opt_in_or_exit",)


def opt_in_or_exit() -> None:
    """Silently ``sys.exit(0)`` unless the project has opted in.

    Short-circuits when:
    1. ``CLAUDE_INVOKED_BY`` is set — recursive hook from flush.py.
    2. ``CLAUDE_PROJECT_DIR`` is empty/unset — no project context.
    3. ``.automaton/mnemic/config.toml`` is absent or has ``enabled = false``.
    """
    if os.environ.get(ENV_CLAUDE_INVOKED_BY):
        sys.exit(0)
    project_dir = os.environ.get(ENV_CLAUDE_PROJECT_DIR, "").strip()
    if not project_dir:
        sys.exit(0)
    if not config_io.read_enabled(Path(project_dir)):
        sys.exit(0)
