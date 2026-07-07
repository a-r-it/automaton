"""Entrypoint for the `mnemic:wiki setup` skill.

Each subcommand is one atomic action. Subdir names come from
`core.config.Config` so there is a single source of truth for
wiki/daily/sources subdir names.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from automaton_config import CONFIG_DIR as AUTOMATON_CONFIG_DIR

from scripts.commands import hooks
from scripts.core import errors
from scripts.core.cli import CliContextP, cli_main
from scripts.core.constants import (
    HOOKS_DIRNAME,
    HOOKS_JSON_FILENAME,
    LIBRARIAN_DIR,
    MARKDOWN_GLOB,
    SCHEMA_FILENAME,
    SCHEMA_GLOB,
    SCHEMAS_DIR,
)
from scripts.core.exit_codes import ExitCode

if TYPE_CHECKING:
    from scripts.core.config import Config

__all__ = [
    "cmd_gitignore_apply",
    "cmd_gitignore_eligible",
    "cmd_hooks",
    "cmd_init_tree",
    "cmd_refresh_schemas",
    "cmd_summary",
    "cmd_sync_deps",
    "cmd_verify",
    "main",
]


def cmd_init_tree(config: Config, root: Path) -> int:
    """Create wiki tree under `root`. Idempotent. Copies plugin schemas
    into per-type dirs. Returns 0 on success; raises EnvError on failure."""
    cfg = config
    try:
        wiki = root / cfg.wiki_subdir
        (root / cfg.daily_subdir).mkdir(parents=True, exist_ok=True)
        (root / cfg.sources_subdir).mkdir(parents=True, exist_ok=True)

        plugin_schemas = cfg.compiler_root / LIBRARIAN_DIR / SCHEMAS_DIR
        for plugin_file in sorted(plugin_schemas.glob(MARKDOWN_GLOB)):
            default_dir = _schema_default_dir(plugin_file)
            target_dir = wiki / default_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / SCHEMA_FILENAME
            if not target.exists():
                target.write_text(plugin_file.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError as exc:
        raise errors.EnvError(
            exit_code=ExitCode.ENV_INIT_TREE,
            action="init-tree",
            underlying=str(exc),
            hint="check filesystem permissions in the project directory",
        ) from exc
    return 0


def cmd_hooks(*, enable: bool, root: Path) -> int:
    """Toggle hooks marker. Returns 0 on success; raises EnvError on write failure."""
    if not enable:
        return 0
    hooks.set_marker(root, enabled=True)
    return 0


def cmd_gitignore_eligible(config: Config, root: Path) -> int:
    """Print JSON {"git": bool, "eligible": [str]} to stdout. Always returns 0."""
    if not _is_git_repo(root):
        print(json.dumps({"git": False, "eligible": []}))
        return 0

    cfg = config
    candidates = (AUTOMATON_CONFIG_DIR, cfg.wiki_subdir, cfg.daily_subdir, cfg.sources_subdir)
    eligible = [name for name in candidates if not _is_ignored(root, name)]
    print(json.dumps({"git": True, "eligible": eligible}))
    return 0


def cmd_gitignore_apply(root: Path, dirs: list[str]) -> int:
    """Append `<dir>/` lines to .gitignore with dedup. Raises SkillError if any dir is non-eligible."""
    if not dirs:
        return 0

    for name in dirs:
        if _is_git_repo(root) and _is_ignored(root, name):
            raise errors.SkillError(
                exit_code=ExitCode.AGENT,
                detail=f"gitignore-apply received already-ignored dir {name!r}",
            )

    gitignore = root / ".gitignore"
    existing = gitignore.read_text().splitlines() if gitignore.exists() else []
    existing_set = set(existing)

    to_append = [f"{name}/" for name in dirs if f"{name}/" not in existing_set]

    if to_append:
        with gitignore.open("a", encoding="utf-8") as fh:
            if existing and not gitignore.read_text().endswith("\n"):
                fh.write("\n")
            for line in to_append:
                fh.write(line + "\n")

    print(f"added: {', '.join(to_append) or '(nothing — already present)'}")
    return 0


def cmd_summary(config: Config, root: Path) -> int:
    """Print the final Wiki-activated block. Always returns 0."""
    from scripts.core import config_io as _config_io

    status = "enabled" if _config_io.read_enabled(root) else "disabled"
    cfg = config
    wiki = cfg.wiki_subdir
    daily = cfg.daily_subdir
    sources = cfg.sources_subdir

    print(
        f"""Wiki activated for this project.
  Compiled knowledge: {wiki}/
  Conversation logs:  {daily}/
  External sources:   {sources}/
  Log file:           {wiki}/flush.log

Hooks: {status}  (config: .automaton/mnemic/config.toml)

Toggle hooks later:
  mnemic:wiki hooks enable
  mnemic:wiki hooks disable
  mnemic:wiki hooks status

Hooks are registered by the mnemic plugin. Make sure the plugin is
enabled, then run /reload-plugins (or start a new session) to activate
them. After ending a session, check {wiki}/flush.log to verify
memory capture."""
    )
    return 0


def cmd_sync_deps(config: Config, *, compiler_root: Path | None = None) -> int:
    """Run `uv sync` for the memory project. Returns 0 on success; raises EnvError on failure."""
    target = compiler_root if compiler_root is not None else config.compiler_root
    result = subprocess.run(
        ["uv", "sync", "--directory", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise errors.EnvError(
            exit_code=ExitCode.ENV_SYNC_DEPS,
            action="sync-deps",
            underlying=result.stderr,
            hint="check network and uv project config",
        )
    return 0


def cmd_verify(config: Config, *, plugin_root: Path | None = None) -> int:
    """Confirm hooks.json ships and compile --dry-run succeeds.

    Returns 0 on success; raises PluginError (60 or 61) on broken plugin state.
    """
    root = plugin_root if plugin_root is not None else config.compiler_root.parent
    hooks_json = root / HOOKS_DIRNAME / HOOKS_JSON_FILENAME
    if not hooks_json.is_file():
        raise errors.PluginError(
            exit_code=ExitCode.PLUGIN_MISSING_HOOKS,
            detail=f"hooks.json missing at {hooks_json}",
        )

    compile_wrapper = root / "bin" / "wiki-compile"
    result = subprocess.run(
        [str(compile_wrapper), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise errors.PluginError(
            exit_code=ExitCode.PLUGIN_COMPILE_FAILED,
            detail="compile --dry-run failed",
            raw_stderr=result.stderr,
        )
    return 0


def cmd_refresh_schemas(config: Config, root: Path) -> int:
    """For each plugin schema: diff against user's copy, prompt keep/overwrite.

    Matches user schemas by `type:` frontmatter, not by directory, so
    `git mv decisions/ adr/` does not break the refresh flow.
    """
    cfg = config
    wiki = root / cfg.wiki_subdir
    plugin_schemas = cfg.compiler_root / LIBRARIAN_DIR / SCHEMAS_DIR

    # Index user schemas by type
    user_by_type: dict[str, Path] = {}
    for user_schema in wiki.glob(SCHEMA_GLOB):
        for line in user_schema.read_text(encoding="utf-8").splitlines():
            if line.startswith("type:"):
                user_by_type[line.split(":", 1)[1].strip()] = user_schema
                break

    kept = overwritten = new = 0

    for plugin_file in sorted(plugin_schemas.glob(MARKDOWN_GLOB)):
        type_name = _schema_type(plugin_file)
        plugin_content = plugin_file.read_text(encoding="utf-8")

        # Resolve target path: prefer indexed-by-type location, fall back to default_dir
        if type_name in user_by_type:
            target = user_by_type[type_name]
        else:
            default_dir = _schema_default_dir(plugin_file)
            target_dir = wiki / default_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / SCHEMA_FILENAME
            if not target.exists():
                target.write_text(plugin_content, encoding="utf-8")
                new += 1
                continue

        user_content = target.read_text(encoding="utf-8")
        if user_content == plugin_content:
            kept += 1
            continue

        print(f"\n=== Schema '{type_name}' diff: plugin vs {target.relative_to(root)} ===\n")
        _print_diff(user_content, plugin_content)
        answer = input("[k]eep (default) / [o]verwrite: ").strip().lower()
        if answer == "o":
            backup = target.with_suffix(".md.bak")
            backup.write_text(user_content, encoding="utf-8")
            target.write_text(plugin_content, encoding="utf-8")
            overwritten += 1
        else:
            kept += 1

    print(f"\nSummary: {kept} kept, {overwritten} overwritten, {new} new")
    return 0


def _schema_default_dir(plugin_file: Path) -> str:
    for line in plugin_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("default_dir:"):
            return line.split(":", 1)[1].strip()
    raise errors.EnvError(
        exit_code=ExitCode.GITIGNORE_INVALID,
        action="init-tree",
        underlying=f"{plugin_file}: missing `default_dir:` frontmatter",
        hint="plugin bug — report it",
    )


def _schema_type(plugin_file: Path) -> str:
    for line in plugin_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("type:"):
            return line.split(":", 1)[1].strip()
    raise errors.EnvError(
        exit_code=ExitCode.GITIGNORE_INVALID,
        action="refresh-schemas",
        underlying=f"{plugin_file}: missing `type:` frontmatter",
        hint="plugin bug — report it",
    )


def _print_diff(old: str, new: str) -> None:
    import difflib

    for line in difflib.unified_diff(
        old.splitlines(keepends=False),
        new.splitlines(keepends=False),
        fromfile="user",
        tofile="plugin",
        lineterm="",
    ):
        print(line)


def _is_git_repo(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _is_ignored(root: Path, name: str) -> bool:
    # Query with trailing slash so `check-ignore` matches directory-form
    # patterns like `wiki/` in .gitignore even when the directory doesn't
    # exist on disk yet. Bare-form patterns (`wiki`) also match this query.
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", f"{name}/"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the setup parser.

    --root defaults to None on every subcommand; the body resolves it via
    ctx.config.root so parser construction does not require WIKI_ROOT to
    be set.
    """
    parser = argparse.ArgumentParser(prog="setup", description="mnemic:wiki setup entrypoint")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync-deps", help="Run uv sync for the memory project")

    p_init = sub.add_parser("init-tree", help="Create wiki tree and schema stub")
    p_init.add_argument("--root", type=Path, default=None)

    p_hooks = sub.add_parser("hooks", help="Toggle hooks marker")
    group = p_hooks.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true")
    group.add_argument("--skip", action="store_true")
    p_hooks.add_argument("--root", type=Path, default=None)

    p_eligible = sub.add_parser("gitignore-eligible", help="Print eligible dirs as JSON")
    p_eligible.add_argument("--root", type=Path, default=None)

    p_apply = sub.add_parser("gitignore-apply", help="Append selected dirs to .gitignore")
    p_apply.add_argument("--dirs", required=True, help="csv of dir names")
    p_apply.add_argument("--root", type=Path, default=None)

    sub.add_parser("verify", help="Verify hooks.json + compile dry-run")

    refresh = sub.add_parser(
        "refresh-schemas",
        help="Re-apply plugin schema templates interactively",
    )
    refresh.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root containing the wiki (defaults to WIKI_ROOT).",
    )

    p_summary = sub.add_parser("summary", help="Print activation summary")
    p_summary.add_argument("--root", type=Path, default=None)

    return parser


@cli_main(name="setup", parser_factory=_build_parser)
def main(ctx: CliContextP) -> ExitCode:  # noqa: PLR0911  # inherent: one match arm per subcommand
    args = ctx.args
    root = getattr(args, "root", None) or ctx.config.root
    match args.cmd:
        case "sync-deps":
            return ExitCode(cmd_sync_deps(ctx.config))
        case "init-tree":
            return ExitCode(cmd_init_tree(ctx.config, root=root))
        case "hooks":
            return ExitCode(cmd_hooks(enable=args.enable, root=root))
        case "gitignore-eligible":
            return ExitCode(cmd_gitignore_eligible(ctx.config, root=root))
        case "gitignore-apply":
            dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
            return ExitCode(cmd_gitignore_apply(root=root, dirs=dirs))
        case "verify":
            return ExitCode(cmd_verify(ctx.config))
        case "refresh-schemas":
            return ExitCode(cmd_refresh_schemas(ctx.config, root=root))
        case "summary":
            return ExitCode(cmd_summary(ctx.config, root=root))
        case _:
            raise AssertionError(f"unreachable: {args.cmd!r}")


if __name__ == "__main__":
    sys.exit(main())
