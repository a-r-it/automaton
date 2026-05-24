"""Caveman SessionStart hook entry point.

Config chain: project .automaton/config.toml → ~/.config/automaton/config.toml → defaults.
Emits banner + prompt to stdout when caveman is enabled.
Run via: uv run --directory engine python .../activate.py <project_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from automaton_config import read_file
from automaton_config.errors import ConfigError

DEFAULTS_ENABLED = True
DEFAULTS_MODE = "full"


def main(project_dir: str) -> None:
    project_root = Path(project_dir)
    enabled = DEFAULTS_ENABLED
    mode = DEFAULTS_MODE

    config_paths = [
        project_root / ".automaton" / "config.toml",
        Path.home() / ".config" / "automaton" / "config.toml",
    ]

    for cfg_path in config_paths:
        try:
            cfg = read_file(cfg_path)
        except ConfigError:
            print(
                f"caveman: warning: malformed TOML in {cfg_path}, using defaults",
                file=sys.stderr,
            )
            continue
        if "caveman" in cfg:
            block = cfg["caveman"]
            enabled = block.get("enabled", enabled)
            mode = block.get("mode", mode)
            break

    if not enabled:
        sys.exit(0)

    caveman_dir = Path(__file__).resolve().parent.parent
    prompt_file = caveman_dir / "references" / "prompt.md"
    content = prompt_file.read_text(encoding="utf-8")
    sys.stdout.write(f"CAVEMAN MODE ACTIVE — level: {mode}\n\n{content}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: activate.py <project_dir>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
