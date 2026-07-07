"""Resolved paths + scalar settings for one process.

Config is a frozen dataclass built once at entrypoint time by
load_config(). Pass root= explicitly in tests; omit it in production
(load_config reads WIKI_ROOT from the environment).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.core import config_io
from scripts.core.constants import (
    DEFAULT_COMPILE_AFTER_HOUR,
    DEFAULT_DAILY_SUBDIR,
    DEFAULT_SOURCES_SUBDIR,
    DEFAULT_WIKI_SUBDIR,
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


def load_config(*, root: Path | None = None) -> Config:
    """Resolve configuration from .automaton/mnemic/config.toml.

    If root is None, reads WIKI_ROOT from the environment. Raises
    ConfigError when WIKI_ROOT is unset or empty. Missing config.toml
    or absent fields fall back to defaults.
    """
    if root is None:
        root_str = os.environ.get(ENV_WIKI_ROOT, "").strip()
        if not root_str:
            raise ConfigError(key=ENV_WIKI_ROOT, reason="unset or empty")
        root = Path(root_str).resolve()
    else:
        root = root.resolve()

    raw = config_io.read_config_toml(root)

    paths_raw = raw.get("paths")
    paths: dict[str, Any] = paths_raw if isinstance(paths_raw, dict) else {}
    compile_raw = raw.get("compile")
    compile_cfg: dict[str, Any] = compile_raw if isinstance(compile_raw, dict) else {}

    wiki_subdir = str(paths.get("wiki", "")).strip() or DEFAULT_WIKI_SUBDIR
    daily_subdir = str(paths.get("daily", "")).strip() or DEFAULT_DAILY_SUBDIR
    sources_subdir = str(paths.get("sources", "")).strip() or DEFAULT_SOURCES_SUBDIR

    hour_raw = compile_cfg.get("after_hour", DEFAULT_COMPILE_AFTER_HOUR)
    if not isinstance(hour_raw, int) or isinstance(hour_raw, bool):
        raise ConfigError(
            key="compile.after_hour",
            reason=f"not an integer: {hour_raw!r}",
        )
    if not (0 <= hour_raw <= 23):
        raise ConfigError(
            key="compile.after_hour",
            reason=f"out of range 0..23: {hour_raw}",
        )

    scripts_dir = Path(__file__).resolve().parent.parent  # memory/scripts/
    compiler_root = scripts_dir.parent  # memory/
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
        scripts=scripts_dir,
        compiler_root=compiler_root,
        hooks=compiler_root / "hooks",
        static_prompt_file=compiler_root / LIBRARIAN_DIR / STATIC_PROMPT_FILENAME,
        compile_after_hour=hour_raw,
    )


def now_iso() -> str:
    """Current time in ISO 8601 format with local offset."""
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    """Current date in YYYY-MM-DD format."""
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
