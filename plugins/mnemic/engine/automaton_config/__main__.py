"""CLI entry point: python -m automaton_config."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from automaton_config.io import read


def _resolve_root(args_root: str | None) -> Path:
    if args_root:
        return Path(args_root)
    env_root = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    return Path(env_root) if env_root else Path.cwd()


def _cmd_get(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    cfg = read(root)
    parts = args.key.split(".")
    val: object = cfg
    for part in parts:
        if not isinstance(val, dict) or part not in val:
            if args.default is not None:
                print(args.default)
                return 0
            return 1
        val = val[part]
    print(val)
    return 0


def _cmd_is_enabled(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    cfg = read(root)
    return 0 if cfg.get("enabled") is True else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="mnemic-config")
    sub = parser.add_subparsers(dest="command")

    get_parser = sub.add_parser("get")
    get_parser.add_argument("key")
    get_parser.add_argument("--default", default=None)
    get_parser.add_argument("--root", default=None)

    enabled_parser = sub.add_parser("is-enabled")
    enabled_parser.add_argument("--root", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 2

    match args.command:
        case "get":
            return _cmd_get(args)
        case "is-enabled":
            return _cmd_is_enabled(args)
        case _:
            parser.print_help()
            return 2


if __name__ == "__main__":
    sys.exit(main())
