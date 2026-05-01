"""Wire contract for stderr error payload + diagnostic logger.

Declares two orthogonal artifacts:

1. LogMode + setup_logger — the diagnostic logger used for arbitrary
   log.info/log.debug events. NOT the user-facing error sink.
2. ErrorCode + per-category payload dataclasses + write_error_payload
   — the wire contract written to stderr on WikiError escape.

Source-of-truth rule for stderr: on a WikiError escape the decorator
writes exactly ONE artifact to stderr — render(err) in human mode, or
the serialized error payload in JSON mode. The diagnostic logger does
NOT duplicate that write.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, TextIO

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.core.errors import WikiError

__all__ = (
    "ERROR_PAYLOAD_SCHEMA_VERSION",
    "AnyErrorPayload",
    "EnvErrorPayload",
    "ErrorCode",
    "FileErrorPayload",
    "LogMode",
    "MissingDependencyPayload",
    "PluginErrorPayload",
    "SimpleErrorPayload",
    "SkillErrorPayload",
    "StageErrorPayload",
    "payload_for",
    "resolve_log_mode",
    "setup_logger",
    "write_error_payload",
)

ENV_LOG_FORMAT = "AUTOMATON_LOG_FORMAT"
ERROR_PAYLOAD_SCHEMA_VERSION = 1


class LogMode(StrEnum):
    HUMAN = "human"
    JSON = "json"


class ErrorCode(StrEnum):
    """Stable wire-contract identifier for each WikiError category.

    Values are decoupled from Python class names by design; class renames
    do NOT change ErrorCode values. New categories add new values; that
    is additive and does not bump schema_version.
    """

    MISSING_DEPENDENCY = "missing_dependency"
    ENV = "env"
    SKILL = "skill"
    PLUGIN = "plugin"
    FILE_WRITE = "file_write"
    FILE_CREATE = "file_create"
    DIR_CREATE = "dir_create"
    CONFIG = "config"
    AGENT = "agent"
    PROMPT = "prompt"


# ─── Log-mode resolution ─────────────────────────────────────────────


def resolve_log_mode(
    *,
    explicit: str | None = None,
    stream: TextIO | None = None,
    env: dict[str, str] | None = None,
    for_file: bool = False,
) -> LogMode:
    """Pick log mode by precedence: explicit > env var > TTY (stream) | HUMAN (file).

    ``for_file=True`` short-circuits the TTY-detection branch and returns
    HUMAN unconditionally (after explicit / env precedence). Use this for
    file sinks — files are never TTYs, and JSON-on-file changes a
    user-visible artifact format as a side effect of refactoring.
    """
    if explicit:
        return LogMode(explicit)
    e = env if env is not None else os.environ
    override = e.get(ENV_LOG_FORMAT, "").strip().lower()
    if override:
        return LogMode(override)
    if for_file:
        return LogMode.HUMAN
    s = stream if stream is not None else sys.stderr
    try:
        is_tty = s.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    return LogMode.HUMAN if is_tty else LogMode.JSON


# ─── Logger formatters ───────────────────────────────────────────────


class _JsonFormatter(logging.Formatter):
    """One JSON object per log record, newline-terminated."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, object] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "name": record.name,
            "event": str(record.msg),
            "message": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


class _HumanFormatter(logging.Formatter):
    def __init__(self, name: str) -> None:
        super().__init__(
            fmt=f"%(asctime)s %(levelname)s [{name}] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def setup_logger(
    name: str,
    mode: LogMode,
    *,
    log_file: Path | None = None,
) -> logging.Logger:
    """Build a per-command diagnostic logger writing to stderr and/or a file.

    When ``log_file`` is set, attach a FileHandler in addition to the
    stderr StreamHandler. The same formatter is used on both handlers —
    one mode value drives both sinks.

    Idempotency: a FileHandler is attached at most once per (name,
    resolved log_file path) pair. If the same name is later called with
    a different ``log_file``, a NEW FileHandler is attached for the new
    path (existing handlers retained — historical sinks keep flowing).
    Subsequent calls with the same path no-op the handler attachment.
    Formatter on every existing handler is updated to match the current
    ``mode`` so a reconfiguration call rotates format consistently.
    Passing ``log_file=None`` when the logger already has a FileHandler
    retains that handler and rotates its formatter to match the current
    ``mode``.
    """
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    log.propagate = False
    formatter: logging.Formatter = (
        _JsonFormatter() if mode is LogMode.JSON else _HumanFormatter(name)
    )
    has_stderr = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in log.handlers
    )
    if not has_stderr:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        log.addHandler(stderr_handler)
    if log_file is not None:
        # FileHandler.baseFilename is always absolute (Python normalises
        # at handler-construction time). Resolve so a caller passing a
        # relative path does not produce a duplicate handler when a
        # previous call passed the absolute equivalent.
        target = str(log_file.resolve())
        already = any(
            isinstance(h, logging.FileHandler) and h.baseFilename == target for h in log.handlers
        )
        if not already:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(target)
            file_handler.setFormatter(formatter)
            log.addHandler(file_handler)
    for h in log.handlers:
        h.setFormatter(formatter)
    return log


# ─── Payload dataclasses ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _PayloadBase:
    """Common fields on every wire-contract error payload."""

    schema_version: ClassVar[int] = ERROR_PAYLOAD_SCHEMA_VERSION
    code: ErrorCode
    exit_code: int
    operation: str
    message: str

    def to_json(self) -> dict[str, object]:
        d = asdict(self)
        d["schema_version"] = self.schema_version
        d["code"] = self.code.value
        return d


@dataclass(frozen=True, slots=True)
class SimpleErrorPayload(_PayloadBase):
    """Forward-compat stub for future categories with no extra fields."""


@dataclass(frozen=True, slots=True)
class MissingDependencyPayload(_PayloadBase):
    tool: str
    install_url: str


@dataclass(frozen=True, slots=True)
class EnvErrorPayload(_PayloadBase):
    action: str
    underlying: str
    hint: str


@dataclass(frozen=True, slots=True)
class SkillErrorPayload(_PayloadBase):
    detail: str


@dataclass(frozen=True, slots=True)
class PluginErrorPayload(_PayloadBase):
    detail: str
    raw_stderr: str | None


@dataclass(frozen=True, slots=True)
class FileErrorPayload(_PayloadBase):
    """Shared shape for FILE_WRITE/FILE_CREATE/DIR_CREATE."""

    path: str
    errno: int
    reason: str


@dataclass(frozen=True, slots=True)
class StageErrorPayload(_PayloadBase):
    """Shared shape for AGENT and PROMPT categories."""

    stage: str
    detail: str  # underlying (AgentError) or reason (PromptError)


type AnyErrorPayload = (
    SimpleErrorPayload
    | MissingDependencyPayload
    | EnvErrorPayload
    | SkillErrorPayload
    | PluginErrorPayload
    | FileErrorPayload
    | StageErrorPayload
)


def payload_for(err: WikiError, *, human: str) -> AnyErrorPayload:  # noqa: PLR0911  # inherent: one match arm per error subclass
    """Build the payload dataclass for this WikiError subclass."""
    # Import inside function to avoid circular import: core.errors imports
    # from core.logging, so core.logging cannot import core.errors at module scope.
    from scripts.core.errors import (
        AgentError,
        ConfigError,
        DirCreateError,
        EnvError,
        FileCreateError,
        FileWriteError,
        MissingDependency,
        PluginError,
        PromptError,
        SkillError,
    )

    common: dict[str, object] = {
        "code": err.payload_code,
        "exit_code": int(err.exit_code),
        "operation": err.operation,
        "message": human,
    }
    match err:
        case MissingDependency(tool=tool, install_url=url):
            # mypy cannot narrow **common kwargs through match dispatch.
            return MissingDependencyPayload(**common, tool=tool, install_url=url)  # type: ignore[arg-type]
        case EnvError(action=a, underlying=u, hint=h):
            return EnvErrorPayload(**common, action=a, underlying=u, hint=h)  # type: ignore[arg-type]
        case SkillError(detail=d):
            return SkillErrorPayload(**common, detail=d)  # type: ignore[arg-type]
        case PluginError(detail=d, raw_stderr=raw):
            return PluginErrorPayload(**common, detail=d, raw_stderr=raw)  # type: ignore[arg-type]
        case (
            FileWriteError(path=p, reason=r, errno=e)
            | FileCreateError(path=p, reason=r, errno=e)
            | DirCreateError(path=p, reason=r, errno=e)
        ):
            return FileErrorPayload(**common, path=str(p), errno=e, reason=r)  # type: ignore[arg-type]
        case ConfigError(key=k, reason=r):
            # ConfigError has no dedicated payload shape — pack (key, reason)
            # into SkillErrorPayload.detail. Consumers dispatch on `code`
            # (ErrorCode.CONFIG), not on `detail` shape.
            return SkillErrorPayload(**common, detail=f"{k}: {r}")  # type: ignore[arg-type]
        case AgentError(stage=s, underlying=u):
            return StageErrorPayload(**common, stage=s, detail=u)  # type: ignore[arg-type]
        case PromptError(stage=s, reason=r):
            return StageErrorPayload(**common, stage=s, detail=r)  # type: ignore[arg-type]
        case _:
            raise AssertionError(f"no payload mapping for {type(err).__name__}")


def write_error_payload(
    err: WikiError,
    *,
    human: str,
    stream: TextIO | None = None,
) -> None:
    """Serialize WikiError as one newline-terminated JSON line to stream.

    Best-effort: swallow OSError/ValueError on write/flush so the caller
    can still return err.exit_code unchanged. Resolution of stream=None:
    prefer current sys.stderr, fall back to sys.__stderr__, final silent
    drop (the exit code alone signals failure).
    """
    target: TextIO | None = stream if stream is not None else sys.stderr
    if target is None:
        target = sys.__stderr__
    if target is None:
        return  # nowhere to write; exit code alone signals failure
    payload = payload_for(err, human=human)
    line = json.dumps(payload.to_json(), ensure_ascii=False) + "\n"
    try:
        target.write(line)
        target.flush()
    except (OSError, ValueError):
        return
