"""Authoritative ExitCode table for memory/scripts.

Single source of truth for process exit codes raised by entrypoints
(setup.py, hooks.py, flush.py, ...) and consumed by bin/ wrappers and
skill refs. Leaf module — no deps on other memory/scripts/ modules.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ("ExitCode",)


class ExitCode(IntEnum):
    """Process exit codes surfaced to shell wrappers and the skill layer.

    Ranges (reserved for future growth):
        0       — success
        10-19   — missing external tooling (uv, etc.)
        20-29   — environment + config resolution
        30-39   — setup / init failure (wiki tree, gitignore)
        40-49   — hooks subsystem (marker toggle)
        50-59   — agent / LLM failure
        60-69   — plugin broken (files missing, smoke-test failed)
        70-79   — command succeeded but surfaced findings (lint, audit, …)
        130     — POSIX signal-derived codes (128 + SIGINT=2)
    """

    OK = 0

    # 10-19 — external tooling missing
    MISSING_UV = 10

    # 20-29 — environment + config resolution
    ENV_SYNC_DEPS = 20
    FILE_WRITE = 21
    FILE_CREATE = 22
    DIR_CREATE = 23
    CONFIG = 24

    # 30-39 — setup / init failure
    ENV_INIT_TREE = 30
    GITIGNORE_INVALID = 31

    # 40-49 — hooks subsystem
    HOOKS_TOGGLE = 40

    # 50-59 — agent / LLM failure
    AGENT = 50
    PROMPT = 51

    # 60-69 — plugin broken
    PLUGIN_MISSING_HOOKS = 60
    PLUGIN_COMPILE_FAILED = 61

    # 70-79 — command succeeded but surfaced findings
    LINT_ERRORS_FOUND = 70

    # POSIX-standard signal-derived codes
    INTERRUPTED = 130  # 128 + SIGINT=2
