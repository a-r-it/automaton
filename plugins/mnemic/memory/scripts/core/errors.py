"""Typed error hierarchy rooted at WikiError.

Every subclass declares two class-level constants:
    exit_code     — ExitCode, process exit value
    payload_code  — ErrorCode, wire-contract string for stderr JSON

Instances carry `operation` — a short, machine-stable label describing
what was being attempted. Never contains user content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from scripts.core.exit_codes import ExitCode
from scripts.core.logging import ErrorCode

if TYPE_CHECKING:
    from pathlib import Path

__all__ = (
    "REPORT_URL",
    "AgentError",
    "ConfigError",
    "DirCreateError",
    "EnvError",
    "FileCreateError",
    "FileWriteError",
    "MissingDependency",
    "PluginError",
    "PromptError",
    "SkillError",
    "WikiError",
    "render",
)

REPORT_URL = "https://github.com/a-r-it/automaton/issues"


class WikiError(Exception):
    """Base for every expected, exit-code-worthy error in memory/scripts/."""

    exit_code: ClassVar[ExitCode]
    payload_code: ClassVar[ErrorCode]
    operation: str


class MissingDependency(WikiError):  # noqa: N818 — category name per design
    """External tool (e.g. uv) required by the plugin is not installed."""

    exit_code: ClassVar[ExitCode] = ExitCode.MISSING_UV
    payload_code: ClassVar[ErrorCode] = ErrorCode.MISSING_DEPENDENCY

    def __init__(self, *, exit_code: ExitCode, tool: str, install_url: str) -> None:
        super().__init__(f"{tool} missing")
        # Instance attribute shadows the class default so each raise keeps
        # its own exit_code even if callers pass different values.
        self.exit_code = exit_code  # type: ignore[misc]
        self.tool = tool
        self.install_url = install_url
        self.operation = f"dep-check-{tool}"


class EnvError(WikiError):
    """User's environment blocked a setup action (permissions, network, disk)."""

    exit_code: ClassVar[ExitCode] = ExitCode.ENV_SYNC_DEPS
    payload_code: ClassVar[ErrorCode] = ErrorCode.ENV

    def __init__(
        self,
        *,
        exit_code: ExitCode,
        action: str,
        underlying: str,
        hint: str,
    ) -> None:
        super().__init__(f"{action} failed")
        # Instance attribute shadows the class default per-raise.
        self.exit_code = exit_code  # type: ignore[misc]
        self.action = action
        self.underlying = underlying
        self.hint = hint
        self.operation = action


class SkillError(WikiError):
    """Skill passed invalid arguments to the setup script. Retry-candidate."""

    exit_code: ClassVar[ExitCode] = ExitCode.AGENT
    payload_code: ClassVar[ErrorCode] = ErrorCode.SKILL

    def __init__(self, *, exit_code: ExitCode, detail: str) -> None:
        super().__init__(detail)
        # Instance attribute shadows the class default per-raise.
        self.exit_code = exit_code  # type: ignore[misc]
        self.detail = detail
        self.operation = "skill-interface"


class PluginError(WikiError):
    """Plugin files/state are broken. User cannot fix — needs reinstall."""

    exit_code: ClassVar[ExitCode] = ExitCode.PLUGIN_MISSING_HOOKS
    payload_code: ClassVar[ErrorCode] = ErrorCode.PLUGIN

    def __init__(
        self,
        *,
        exit_code: ExitCode,
        detail: str,
        raw_stderr: str | None = None,
    ) -> None:
        super().__init__(detail)
        # Instance attribute shadows the class default per-raise.
        self.exit_code = exit_code  # type: ignore[misc]
        self.detail = detail
        self.raw_stderr = raw_stderr
        self.operation = "plugin-state-check"


class FileWriteError(WikiError):
    """Writing to an existing file failed."""

    exit_code: ClassVar[ExitCode] = ExitCode.FILE_WRITE
    payload_code: ClassVar[ErrorCode] = ErrorCode.FILE_WRITE

    def __init__(
        self,
        *,
        path: Path,
        reason: str,
        errno: int,
        operation: str,
    ) -> None:
        super().__init__(f"write failed: {path}")
        self.path = path
        self.reason = reason
        self.errno = errno
        self.operation = operation


class FileCreateError(WikiError):
    """Creating a new file failed."""

    exit_code: ClassVar[ExitCode] = ExitCode.FILE_CREATE
    payload_code: ClassVar[ErrorCode] = ErrorCode.FILE_CREATE

    def __init__(
        self,
        *,
        path: Path,
        reason: str,
        errno: int,
        operation: str,
    ) -> None:
        super().__init__(f"create failed: {path}")
        self.path = path
        self.reason = reason
        self.errno = errno
        self.operation = operation


class DirCreateError(WikiError):
    """Creating a directory failed."""

    exit_code: ClassVar[ExitCode] = ExitCode.DIR_CREATE
    payload_code: ClassVar[ErrorCode] = ErrorCode.DIR_CREATE

    def __init__(
        self,
        *,
        path: Path,
        reason: str,
        errno: int,
        operation: str,
    ) -> None:
        super().__init__(f"mkdir failed: {path}")
        self.path = path
        self.reason = reason
        self.errno = errno
        self.operation = operation


class ConfigError(WikiError):
    """Required environment / config key is unset, empty, or invalid."""

    exit_code: ClassVar[ExitCode] = ExitCode.CONFIG
    payload_code: ClassVar[ErrorCode] = ErrorCode.CONFIG

    def __init__(self, *, key: str, reason: str) -> None:
        super().__init__(f"config error: {key}: {reason}")
        self.key = key
        self.reason = reason
        self.operation = f"config-resolve-{key}"


class AgentError(WikiError):
    """Claude Agent SDK call failed (non-recoverable, report stage + cause)."""

    exit_code: ClassVar[ExitCode] = ExitCode.AGENT
    payload_code: ClassVar[ErrorCode] = ErrorCode.AGENT

    def __init__(self, *, stage: str, underlying: str) -> None:
        super().__init__(f"agent {stage} failed: {underlying}")
        self.stage = stage
        self.underlying = underlying
        self.operation = f"agent-{stage}"


class PromptError(WikiError):
    """Prompt rendering / assembly failed (missing schema, bad template)."""

    exit_code: ClassVar[ExitCode] = ExitCode.PROMPT
    payload_code: ClassVar[ErrorCode] = ErrorCode.PROMPT

    def __init__(self, *, stage: str, reason: str) -> None:
        super().__init__(f"prompt {stage} failed: {reason}")
        self.stage = stage
        self.reason = reason
        self.operation = f"prompt-{stage}"


def render(err: WikiError) -> str:  # noqa: C901, PLR0911  # inherent: one match arm per error subclass
    """Format user-facing stderr text for any WikiError subclass."""
    match err:
        case MissingDependency(tool=tool, install_url=url):
            return f"{tool} is required but not installed. Install from {url}"
        case EnvError(action=action, underlying=under, hint=hint):
            return f"{action} failed: {under} ({hint})"
        case SkillError(detail=detail):
            return f"skill bug: {detail}. please report at {REPORT_URL}."
        case PluginError(detail=detail, raw_stderr=None):
            return f"plugin is broken: {detail}. please report at {REPORT_URL}."
        case PluginError(detail=detail, raw_stderr=raw):
            short = (raw or "").splitlines()[0][:200]
            return f"plugin is broken: {detail}. please report at {REPORT_URL}. details: {short}"
        case FileWriteError(path=p, reason=r, operation=op):
            return f"failed to write {p} during {op}: {r}"
        case FileCreateError(path=p, reason=r, operation=op):
            return f"failed to create {p} during {op}: {r}"
        case DirCreateError(path=p, reason=r, operation=op):
            return f"failed to mkdir {p} during {op}: {r}"
        case ConfigError(key=k, reason=r):
            return f"config error: {k}: {r}"
        case AgentError(stage=s, underlying=u):
            return f"agent {s} failed: {u}"
        case PromptError(stage=s, reason=r):
            return f"prompt {s} failed: {r}"
        case _:
            raise AssertionError(f"unhandled WikiError: {type(err).__name__}")
