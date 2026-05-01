"""Toggle automation hooks marker for the automaton plugin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.core import errors
from scripts.core.cli import CliContextP, cli_main
from scripts.core.constants import AUTOMATON_MARKER_FILENAME, CLAUDE_DIR
from scripts.core.exit_codes import ExitCode

__all__ = ("cmd_disable", "cmd_enable", "cmd_status", "main", "set_marker")

_MARKER_PATH = Path(CLAUDE_DIR) / AUTOMATON_MARKER_FILENAME


def set_marker(root: Path, *, enabled: bool) -> bool:
    """Create/remove marker at root/.claude/automaton.enabled.

    Returns True if state changed, False if already in the target state.
    Raises OSError on filesystem failure; callers wrap in EnvError.
    """
    marker = root / _MARKER_PATH
    existed = marker.is_file()
    if enabled:
        if existed:
            return False
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return True
    if not existed:
        return False
    marker.unlink()
    return True


def cmd_status(root: Path) -> int:
    """Print current hook marker state. Always returns 0."""
    state = "enabled" if (root / _MARKER_PATH).is_file() else "disabled"
    print(f"hooks: {state}")
    return 0


def cmd_enable(root: Path) -> int:
    """Create the hooks marker. Returns 0; idempotent. Raises EnvError on filesystem failure."""
    try:
        changed = set_marker(root, enabled=True)
    except OSError as exc:
        raise errors.EnvError(
            exit_code=ExitCode.HOOKS_TOGGLE,
            action="hooks enable",
            underlying=str(exc),
            hint="check filesystem permissions in .claude/",
        ) from exc
    print("hooks: enabled" + ("" if changed else " (already)"))
    return 0


def cmd_disable(root: Path) -> int:
    """Remove the hooks marker. Returns 0; idempotent. Raises EnvError on filesystem failure."""
    try:
        changed = set_marker(root, enabled=False)
    except OSError as exc:
        raise errors.EnvError(
            exit_code=ExitCode.HOOKS_TOGGLE,
            action="hooks disable",
            underlying=str(exc),
            hint="check filesystem permissions in .claude/",
        ) from exc
    print("hooks: disabled" + ("" if changed else " (already)"))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Return argparse parser with --root and subcommand choices.

    --root defaults to None; the body resolves it via ctx.config.root so
    parser construction does not require WIKI_ROOT to be set.
    """
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--root", type=Path, default=None)

    parser = argparse.ArgumentParser(
        prog="hooks",
        description="Toggle automaton hooks marker",
        parents=[shared],
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("enable", help="Create .claude/automaton.enabled", parents=[shared])
    sub.add_parser("disable", help="Remove .claude/automaton.enabled", parents=[shared])
    sub.add_parser("status", help="Print current marker state", parents=[shared])
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
