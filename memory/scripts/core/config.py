"""Resolved paths + scalar settings for one process.

Config is a frozen dataclass built once at entrypoint time by
load_config(). Tests construct overrides directly; production @cli_main
decorator injects via CliContext.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts.core.constants import (
    DEFAULT_COMPILE_AFTER_HOUR,
    DEFAULT_DAILY_SUBDIR,
    DEFAULT_SOURCES_SUBDIR,
    DEFAULT_WIKI_SUBDIR,
    ENV_OPT_COMPILE_AFTER_HOUR,
    ENV_OPT_DAILY_DIR,
    ENV_OPT_SOURCES_DIR,
    ENV_OPT_WIKI_DIR,
    ENV_WIKI_ROOT,
    INDEX_FILENAME,
    LIBRARIAN_DIR,
    LINT_REPORTS_DIR,
    LOG_FILENAME,
    STATE_FILENAME,
    STATIC_PROMPT_FILENAME,
)
from scripts.core.errors import ConfigError

__all__ = (
    "TIMEZONE",
    "Config",
    "load_config",
    "now_iso",
    "today_iso",
)


TIMEZONE = "Europe/Moscow"


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration for one process.

    All path fields are absolute. Raw subdir strings are preserved
    alongside the resolved Paths so callers that need e.g. prompt
    placeholder substitution can use the original string (including
    nested values like "knowledge/wiki").
    """

    # data roots
    root: Path
    wiki: Path
    daily: Path
    sources: Path
    reports: Path
    # raw subdir strings preserved for nested paths like "knowledge/wiki"
    wiki_subdir: str
    daily_subdir: str
    sources_subdir: str
    # data files
    state_file: Path
    log_file: Path
    # code roots
    scripts: Path
    compiler_root: Path
    hooks: Path
    static_prompt_file: Path
    # scalars
    compile_after_hour: int

    @property
    def index_file(self) -> Path:
        return self.wiki / INDEX_FILENAME

    @property
    def knowledge(self) -> Path:
        return self.wiki


def load_config(*, env: dict[str, str] | None = None) -> Config:
    """Resolve configuration from environment.

    Unset or empty WIKI_ROOT raises ConfigError instead of silently
    falling back to Path.cwd(). This fixes the footgun documented in
    CLAUDE.md where `cd memory/ && python scripts/...` creates a stray
    memory/wiki/ tree. Hooks, wrappers, and skill dispatch all set
    WIKI_ROOT explicitly.
    """
    e = env if env is not None else os.environ
    root_str = e.get(ENV_WIKI_ROOT, "").strip()
    if not root_str:
        raise ConfigError(key=ENV_WIKI_ROOT, reason="unset or empty")
    root = Path(root_str).resolve()

    wiki_subdir = e.get(ENV_OPT_WIKI_DIR, "").strip() or DEFAULT_WIKI_SUBDIR
    daily_subdir = e.get(ENV_OPT_DAILY_DIR, "").strip() or DEFAULT_DAILY_SUBDIR
    sources_subdir = e.get(ENV_OPT_SOURCES_DIR, "").strip() or DEFAULT_SOURCES_SUBDIR

    hour_str = e.get(ENV_OPT_COMPILE_AFTER_HOUR, "").strip()
    try:
        hour = int(hour_str) if hour_str else DEFAULT_COMPILE_AFTER_HOUR
    except ValueError as exc:
        raise ConfigError(
            key=ENV_OPT_COMPILE_AFTER_HOUR,
            reason=f"not an integer: {hour_str!r}",
        ) from exc
    if not (0 <= hour <= 23):
        raise ConfigError(
            key=ENV_OPT_COMPILE_AFTER_HOUR,
            reason=f"out of range 0..23: {hour}",
        )

    scripts = Path(__file__).resolve().parent.parent  # memory/scripts/
    compiler_root = scripts.parent  # memory/
    wiki = root / wiki_subdir

    return Config(
        root=root,
        wiki=wiki,
        daily=root / daily_subdir,
        sources=root / sources_subdir,
        reports=root / LINT_REPORTS_DIR,
        wiki_subdir=wiki_subdir,
        daily_subdir=daily_subdir,
        sources_subdir=sources_subdir,
        state_file=wiki / STATE_FILENAME,
        log_file=wiki / LOG_FILENAME,
        scripts=scripts,
        compiler_root=compiler_root,
        hooks=compiler_root / "hooks",
        static_prompt_file=compiler_root / LIBRARIAN_DIR / STATIC_PROMPT_FILENAME,
        compile_after_hour=hour,
    )


def now_iso() -> str:
    """Current time in ISO 8601 format with local offset."""
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current date in YYYY-MM-DD format."""
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
