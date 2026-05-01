"""
Compile daily conversation logs and external sources into structured knowledge articles.

This is the "LLM compiler" — it reads input files (daily logs or external sources)
and produces organized, typed wiki articles.

Usage:
    uv run python compile.py                    # compile new/changed files only
    uv run python compile.py --all              # force recompile everything
    uv run python compile.py --file daily/2026-04-01.md  # compile a specific file
    uv run python compile.py --dry-run          # show what would be compiled
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.core.agent import COMPILE_OPTIONS, run_agent
from scripts.core.cli import CliContextP, cli_main
from scripts.core.constants import (
    FLUSH_LOG_FILENAME,
    INDEX_FILENAME,
    LIBRARIAN_DIR,
    LINT_REPORT_GLOB,
    LOG_FILENAME,
    MARKDOWN_GLOB,
    SCHEMA_GLOB,
    STATIC_PROMPT_FILENAME,
    SourceType,
)
from scripts.core.errors import AgentError, FileCreateError, WikiError
from scripts.core.exit_codes import ExitCode
from scripts.core.redact import redact as _redact_text
from scripts.core.render import load_schemas, render_prompt
from scripts.core.utils import (
    list_daily_files,
    list_source_files,
    list_wiki_articles,
    read_wiki_index,
    sha256_file,
    update_state,
)
from scripts.prompts import build_compile

if TYPE_CHECKING:
    from scripts.core.config import Config

log = logging.getLogger(__name__)


def read_latest_lint_report(config: Config) -> str:
    """Return the body of the most recent lint report, or "" if none exists.

    Never raises. Picks the file with the greatest mtime among
    ``lint/lint-*.md``.
    """
    reports = config.reports
    if not reports.exists():
        return ""
    candidates = sorted(
        reports.glob(LINT_REPORT_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return ""
    try:
        content: str = candidates[0].read_text(encoding="utf-8")
    except OSError:
        return ""
    else:
        return content


def _peek_type(schema_path: Path) -> str:
    """Read just the `type:` frontmatter field from a schema file."""
    for line in schema_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("type:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError(f"{schema_path}: missing `type:` frontmatter")


def _redact_modified_wiki_files(config: Config, snapshot: dict[Path, float]) -> None:
    """Redact secrets in wiki files that were written/modified after snapshot.

    Args:
        config: Resolved project configuration.
        snapshot: {Path: mtime_float} captured before compile_file() ran.
                  Files with mtime > snapshot[path] (or absent from snapshot)
                  are considered newly written and will be scanned.
    """
    wiki = config.wiki
    for path in wiki.rglob(MARKDOWN_GLOB):
        try:
            if not path.exists():
                continue
            if path.stat().st_mtime <= snapshot.get(path, 0):
                continue  # file predates this compile run

            content = path.read_text(encoding="utf-8")
            redacted, notices = _redact_text(content)
            if notices:
                path.write_text(redacted, encoding="utf-8")
                for notice in notices:
                    rel = path.relative_to(wiki)
                    log.warning("REDACTED in %s: %s", rel, notice)
                    print(f"  REDACTED: {notice} in {rel}")
        except (OSError, UnicodeDecodeError) as exc:
            log.warning("Failed to redact %s: %s", path, exc)


async def compile_file(
    config: Config,
    file_entry: dict[str, Any],
    source_type: SourceType,
) -> float:
    """Compile a single file (daily log or source document). Returns API cost."""
    cfg = config
    file_path: Path = file_entry["path"]
    file_hash: str = file_entry["hash"]
    file_content = file_path.read_text(encoding="utf-8")  # noqa: ASYNC240  # CLI tool; local I/O is negligible vs. LLM call
    wiki_index = read_wiki_index(config)
    lint_report = read_latest_lint_report(config)

    existing_articles: dict[str, str] = {}
    for article_path in list_wiki_articles(config):
        rel = article_path.relative_to(cfg.wiki)
        existing_articles[str(rel)] = article_path.read_text(encoding="utf-8")

    registry = load_schemas(cfg.wiki)
    static_md = (cfg.compiler_root / LIBRARIAN_DIR / STATIC_PROMPT_FILENAME).read_text(
        encoding="utf-8"
    )
    rendered_schema = render_prompt(
        registry,
        static_md,
        wiki=cfg.wiki_subdir,
        daily=cfg.daily_subdir,
        sources=cfg.sources_subdir,
    )
    type_to_dir = {
        schema.type: path.parent.name
        for path in cfg.wiki.glob(SCHEMA_GLOB)
        for schema in [registry[_peek_type(path)]]
    }

    prompt = build_compile(
        file_path=file_path,
        source_type=source_type,
        wiki_index=wiki_index,
        existing_articles=existing_articles,
        file_content=file_content,
        rendered_schema=rendered_schema,
        type_to_dir=type_to_dir,
        wiki_dir=cfg.wiki,
        lint_report=lint_report,
        index_filename=INDEX_FILENAME,
        log_filename=LOG_FILENAME,
    )

    cost = 0.0
    try:
        result = await run_agent(prompt, cwd=cfg.root, options=COMPILE_OPTIONS)
        cost = result.cost_usd
        print(f"  Cost: ${cost:.4f}")
    except Exception as e:
        # Do NOT swallow — the caller tracks had_failure to keep batch
        # semantics (process remaining files) while still raising at the
        # end so the process exit code and stderr payload honour the
        # wire contract. See Task 15 follow-up.
        print(f"  Error: {e}")
        raise AgentError(
            stage=f"compile-file:{Path(str(file_path)).name}",
            underlying=str(e),
        ) from e

    update_state(config, file_path, file_hash, source_type=source_type)
    return cost


def _collect_to_compile(
    config: Config,
    args: argparse.Namespace,
    target: Path | None,
    source_type: SourceType | None,
) -> list[dict[str, Any]]:
    """Build the list of file entries to compile based on CLI args."""
    if args.file:
        if target is None or source_type is None:
            raise AssertionError("target and source_type must be set when args.file is truthy")
        return [{"path": target, "hash": sha256_file(target), "source_type": source_type}]
    daily_entries = list_daily_files(config, changed_only=not args.all)
    source_entries = list_source_files(config, new_only=not args.all)
    return [{"source_type": "daily", **f} for f in daily_entries] + [
        {"source_type": "source", **f} for f in source_entries
    ]


async def _compile_batch(
    config: Config,
    to_compile: list[dict[str, Any]],
) -> None:
    """Compile each entry in the batch; raise AgentError if any fail."""
    cfg = config
    total_cost = 0.0
    failed: list[str] = []
    for i, entry in enumerate(to_compile, 1):
        print(
            f"\n[{i}/{len(to_compile)}] Compiling {entry['path'].name} ({entry['source_type']})..."
        )
        snapshot = {p: p.stat().st_mtime for p in cfg.wiki.rglob(MARKDOWN_GLOB) if p.exists()}
        try:
            cost = await compile_file(config, entry, entry["source_type"])
        except AgentError as exc:
            # Preserve batch semantics: continue with remaining files,
            # but remember the failure so we raise at the end with a
            # typed WikiError (honouring the wire contract).
            failed.append(str(exc))
            _redact_modified_wiki_files(config, snapshot)
            continue
        _redact_modified_wiki_files(config, snapshot)
        total_cost += cost
        print("  Done.")

    if failed:
        raise AgentError(
            stage="compile-run",
            underlying=f"{len(failed)} file(s) failed during compilation: "
            + "; ".join(failed[:3])
            + ("…" if len(failed) > 3 else ""),
        )

    articles = list_wiki_articles(config)
    print(f"\nCompilation complete. Total cost: ${total_cost:.4f}")
    print(f"Knowledge base: {len(articles)} articles")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile daily logs and sources into typed wiki articles"
    )
    parser.add_argument("--all", action="store_true", help="Force recompile all files")
    parser.add_argument("--file", type=str, help="Compile a specific file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be compiled")
    return parser


async def _run_compile(config: Config, args: argparse.Namespace) -> None:
    cfg = config
    target: Path | None = None
    source_type: SourceType | None = None
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = cfg.root / args.file
        if not target.exists():
            raise FileCreateError(
                path=Path(args.file),
                reason="not found",
                errno=2,  # ENOENT
                operation="compile-locate-input",
            )
        source_type = "source" if cfg.sources in target.parents else "daily"

    # Configure logging so commit.py output lands in the shared flush.log,
    # matching the format used by flush.py. Use force=True because conftest
    # and tests may have already configured root logger state.
    if cfg.wiki.exists():
        logging.basicConfig(
            filename=str(cfg.wiki / FLUSH_LOG_FILENAME),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            force=True,
        )

    try:
        to_compile = _collect_to_compile(config, args, target, source_type)

        if not to_compile:
            print("Nothing to compile — all files are up to date.")
            return

        label = "[DRY RUN] " if args.dry_run else ""
        print(f"{label}Files to compile ({len(to_compile)}):")
        for f in to_compile:
            print(f"  - [{f['source_type']}] {Path(f['path']).name}")

        if args.dry_run:
            return

        await _compile_batch(config, to_compile)
    finally:
        # Auto-commit wiki/ and daily/ changes regardless of early returns.
        # --dry-run must not commit — so skip in that mode.
        if not args.dry_run:
            from scripts.commands.commit import run as run_commit

            await run_commit(config)


@cli_main(name="compile", parser_factory=build_parser)
async def main(ctx: CliContextP) -> ExitCode:
    try:
        await _run_compile(ctx.config, ctx.args)
    except WikiError:
        raise  # Already-typed failures (FileCreateError, AgentError from compile_file) bubble as-is.
    except Exception as exc:
        raise AgentError(stage="compile-run", underlying=str(exc)) from exc
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
