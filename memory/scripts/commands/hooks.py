"""Toggle automation hooks marker for the automaton plugin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.core import config_io, errors
from scripts.core.cli import CliContextP, cli_main
from scripts.core.exit_codes import ExitCode

__all__ = ("cmd_disable", "cmd_enable", "cmd_status", "main", "set_marker")


def set_marker(root: Path, *, enabled: bool) -> bool:
    """Toggle enabled field in root/.automaton/config.toml.

    Returns True if state changed.
    enable=True with no config.toml → raises EnvError (run setup first).
    disable with no config.toml → returns False (already disabled).
    Raises EnvError on filesystem failure.
    """
    try:
        return config_io.update_enabled(root, enabled=enabled)
    except errors.ConfigError:
        if not enabled:
            return False
        raise errors.EnvError(
            exit_code=ExitCode.HOOKS_TOGGLE,
            action="hooks enable",
            underlying="config.toml not found",
            hint="run `automaton:wiki setup` to create .automaton/config.toml",
        ) from None
    except OSError as exc:
        raise errors.EnvError(
            exit_code=ExitCode.HOOKS_TOGGLE,
            action=f"hooks {'enable' if enabled else 'disable'}",
            underlying=str(exc),
            hint="check filesystem permissions in .automaton/",
        ) from exc


def cmd_status(root: Path) -> int:
    """Print current hook state. Always returns 0."""
    state = "enabled" if config_io.read_enabled(root) else "disabled"
    print(f"hooks: {state}")
    return 0


def cmd_enable(root: Path) -> int:
    """Set enabled=true in config.toml. Returns 0; idempotent."""
    changed = set_marker(root, enabled=True)
    print("hooks: enabled" + ("" if changed else " (already)"))
    return 0


def cmd_disable(root: Path) -> int:
    """Set enabled=false in config.toml. Returns 0; idempotent."""
    changed = set_marker(root, enabled=False)
    print("hooks: disabled" + ("" if changed else " (already)"))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--root", type=Path, default=None)

    parser = argparse.ArgumentParser(
        prog="hooks",
        description="Toggle automaton hooks in .automaton/config.toml",
        parents=[shared],
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("enable", help="Set enabled=true in .automaton/config.toml", parents=[shared])
    sub.add_parser("disable", help="Set enabled=false in .automaton/config.toml", parents=[shared])
    sub.add_parser("status", help="Print current enabled state", parents=[shared])
    return parser


@cli_main(name="hooks", parser_factory=_build_parser)
def main(ctx: CliContextP) -> ExitCode:
    """CLI entry point. Returns ExitCode; decorator handles WikiError dispatch."""
    args = ctx.args
    root = args.root or ctx.config.root
    cmd = args.cmd or "status"
    match cmd:
        case "enable":
            return ExitCode(cmd_enable(root=root))
        case "disable":
            return ExitCode(cmd_disable(root=root))
        case "status":
            return ExitCode(cmd_status(root=root))
        case _:
            raise AssertionError(f"unreachable: {cmd!r}")


if __name__ == "__main__":
    sys.exit(main())
