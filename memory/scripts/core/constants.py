"""Pure literal constants — filenames, env var names, glob patterns, sentinels.

Zero side effects, zero deps on other memory/scripts/ modules. Safe to import
from anywhere (including tests without env setup).
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = (
    "AUTOMATON_CONFIG_DIR",
    "AUTOMATON_CONFIG_FILENAME",
    "COMPILE_LOG_FILENAME",
    "DEFAULT_COMPILE_AFTER_HOUR",
    "DEFAULT_DAILY_SUBDIR",
    "DEFAULT_SOURCES_SUBDIR",
    "DEFAULT_WIKI_SUBDIR",
    "ENV_CLAUDE_INVOKED_BY",
    "ENV_CLAUDE_PROJECT_DIR",
    "ENV_FLUSH_STDERR_LOG",
    "ENV_WIKI_ROOT",
    "FLUSH_LOG_FILENAME",
    "HOOKS_DIRNAME",
    "HOOKS_JSON_FILENAME",
    "INDEX_FILENAME",
    "INTERNAL_ARTICLE_FILES",
    "INVOKED_BY_FLUSH",
    "LAST_FLUSH_FILENAME",
    "LIBRARIAN_DIR",
    "LINT_REPORTS_DIR",
    "LINT_REPORT_FMT",
    "LINT_REPORT_GLOB",
    "LOG_FILENAME",
    "MARKDOWN_GLOB",
    "QA_SUBDIR",
    "SCHEMAS_DIR",
    "SCHEMA_FILENAME",
    "SCHEMA_GLOB",
    "STATE_FILENAME",
    "STATIC_PROMPT_FILENAME",
    "SourceType",
)

# ── Source type sentinel ───────────────────────────────────────────────
type SourceType = Literal["daily", "source"]

# ── Default subdir names (fallbacks when config.toml absent) ─────────
DEFAULT_WIKI_SUBDIR: Final = "wiki"
DEFAULT_DAILY_SUBDIR: Final = "daily"
DEFAULT_SOURCES_SUBDIR: Final = "sources"
DEFAULT_COMPILE_AFTER_HOUR: Final = 18

# ── Filenames ─────────────────────────────────────────────────────────
AUTOMATON_CONFIG_FILENAME: Final = "config.toml"
SCHEMA_FILENAME: Final = "_schema.md"
INDEX_FILENAME: Final = "index.md"
LOG_FILENAME: Final = "log.md"
STATE_FILENAME: Final = "state.json"
LAST_FLUSH_FILENAME: Final = "last-flush.json"
FLUSH_LOG_FILENAME: Final = "flush.log"
COMPILE_LOG_FILENAME: Final = "compile.log"
HOOKS_JSON_FILENAME: Final = "hooks.json"
STATIC_PROMPT_FILENAME: Final = "static.md"

# ── Directory names (relative, composable under ROOT_DIR or COMPILER_ROOT) ──
AUTOMATON_CONFIG_DIR: Final = ".automaton"
LIBRARIAN_DIR: Final = "librarian"
SCHEMAS_DIR: Final = "schemas"
HOOKS_DIRNAME: Final = "hooks"  # plugin hooks dir (not .claude/hooks/)
LINT_REPORTS_DIR: Final = "lint"
QA_SUBDIR: Final = "qa"

# ── Glob patterns / derived formats ───────────────────────────────────
SCHEMA_GLOB: Final = f"*/{SCHEMA_FILENAME}"
MARKDOWN_GLOB: Final = "*.md"
LINT_REPORT_GLOB: Final = "lint-*.md"
LINT_REPORT_FMT: Final = "lint-{date}.md"

# Files inside an article-dir that are NOT articles (exclude from dir scans).
INTERNAL_ARTICLE_FILES: Final = frozenset({SCHEMA_FILENAME, INDEX_FILENAME})

# ── Env var NAMES (keys, not values) ──────────────────────────────────
ENV_WIKI_ROOT: Final = "WIKI_ROOT"
ENV_CLAUDE_PROJECT_DIR: Final = "CLAUDE_PROJECT_DIR"
ENV_CLAUDE_INVOKED_BY: Final = "CLAUDE_INVOKED_BY"
ENV_FLUSH_STDERR_LOG: Final = "FLUSH_STDERR_LOG"
# ── Sentinel env values ───────────────────────────────────────────────
# Value set in CLAUDE_INVOKED_BY by flush.py to prevent recursive hook firing.
INVOKED_BY_FLUSH: Final = "memory_flush"
