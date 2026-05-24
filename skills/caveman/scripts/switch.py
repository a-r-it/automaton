"""Caveman config switch for /caveman skill.

Read-modify-write of [caveman] block in .automaton/config.toml.
Run via: uv run --directory engine python .../switch.py <mode> [project_dir]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from automaton_config import read, write
from automaton_config.errors import ConfigError

VALID_MODES: frozenset[str] = frozenset({"lite", "full", "ultra", "off"})


def main(mode: str, project_dir: str | None = None) -> None:
    mode = mode.strip().lower()
    if mode not in VALID_MODES:
        sys.exit(1)

    root = Path(project_dir) if project_dir else Path(
        os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    )

    try:
        cfg = read(root)
    except ConfigError:
        cfg = {}

    current_mode = "full"
    if "caveman" in cfg and isinstance(cfg["caveman"], dict):
        current_mode = cfg["caveman"].get("mode", "full")

    if mode == "off":
        cfg["caveman"] = {"enabled": False, "mode": current_mode}
    else:
        cfg["caveman"] = {"enabled": True, "mode": mode}

    write(root, cfg)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: switch.py <mode> [project_dir]", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
