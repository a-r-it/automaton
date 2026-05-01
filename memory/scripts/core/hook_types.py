"""Typed payloads for hook stdin contract.

Claude Code hooks receive a JSON payload on stdin. This module declares
the shape per event (PreCompactPayload, SessionEndPayload) plus an
overloaded parser that validates ``hook_event_name`` against an expected
literal and returns the narrowed payload.

Only events the plugin actually consumes are typed: PreCompact and
SessionEnd. SessionStart does not read stdin (it only writes a context
JSON to stdout) and therefore has no payload type here.

Wire shape derives from Claude Code hook protocol:
https://code.claude.com/docs/en/hooks.md

SessionEnd shape was empirically captured on 2026-04-25 via marker-file
gated tee in bin/hook-session-end. PreCompact shape extrapolated from
SessionEnd convention; verify on next natural auto-compact event.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Literal, TypedDict, overload

__all__ = (
    "HookStdinPayload",
    "PreCompactPayload",
    "SessionEndPayload",
    "parse_hook_input",
)

# Module-level named logger. Errors and mismatches go via "flush" — the
# same logger the hook entrypoints configure with a FileHandler on
# wiki/flush.log. Using `logging.warning(...)` (root logger) here would
# leak via lastResort to stderr after _configure_root_logger deletion.
log = logging.getLogger("flush")


class _BaseHookPayload(TypedDict):
    session_id: str
    transcript_path: str
    cwd: str


class PreCompactPayload(_BaseHookPayload):
    hook_event_name: Literal["PreCompact"]
    # Field name extrapolated from SessionEnd capture (2026-04-25).
    # Documented matcher values: "manual" | "auto". Tolerant `str` until
    # natural auto-compact event confirms — then tighten to Literal.
    reason: str


class SessionEndPayload(_BaseHookPayload):
    hook_event_name: Literal["SessionEnd"]
    # Empirically confirmed field. Captured value: "prompt_input_exit".
    # Documented matcher values: "clear" | "resume" | "logout".
    # Kept tolerant `str` because docs imply non-exhaustive matcher set;
    # closed `Literal` would reject undocumented future reasons.
    reason: str


type HookStdinPayload = PreCompactPayload | SessionEndPayload


@overload
def parse_hook_input(expected: Literal["PreCompact"]) -> PreCompactPayload | None: ...
@overload
def parse_hook_input(expected: Literal["SessionEnd"]) -> SessionEndPayload | None: ...
def parse_hook_input(
    expected: Literal["PreCompact", "SessionEnd"],
) -> HookStdinPayload | None:
    """Read JSON from stdin, validate hook_event_name, return narrowed payload.

    Returns None on:
        - empty stdin / OSError
        - invalid JSON (with one tolerant retry for unescaped backslashes —
          Windows path workaround inherited from the prior parser)
        - hook_event_name mismatch with ``expected`` (misroute defence)
        - missing required fields per the typed shape
    """
    raw = _read_stdin_tolerant()
    if raw is None:
        return None
    if raw.get("hook_event_name") != expected:
        log.warning(
            "hook_event_name mismatch: expected=%s got=%s",
            expected,
            raw.get("hook_event_name"),
        )
        return None
    if not _has_required_fields(raw):
        return None
    # Cast safe: _has_required_fields validates shape; structural narrowing.
    return raw  # type: ignore[return-value]


def _read_stdin_tolerant() -> dict[str, object] | None:
    """Read stdin JSON, retry once on JSONDecodeError after escaping bare backslashes."""
    try:
        text = sys.stdin.read()
    except (OSError, ValueError):
        return None
    if not text:
        return None
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        fixed = re.sub(r'(?<!\\)\\(?!["\\])', r"\\\\", text)
        try:
            result = json.loads(fixed)
        except json.JSONDecodeError:
            log.exception("Failed to parse stdin")
            return None
    return result if isinstance(result, dict) else None


def _has_required_fields(raw: dict[str, object]) -> bool:
    """Verify all required fields present with correct primitive type.

    Both events use `reason` as the discriminator (SessionEnd confirmed
    empirically; PreCompact extrapolated). If PreCompact ground-truth
    turns out to use a different field name, `_has_required_fields`
    returns False → parse_hook_input returns None → fail-open skip.
    """
    needed = {"session_id", "transcript_path", "cwd", "hook_event_name", "reason"}
    missing = needed - raw.keys()
    if missing:
        log.warning("payload missing required fields: %s", sorted(missing))
        return False
    wrong_type = [k for k in needed if not isinstance(raw.get(k), str)]
    if wrong_type:
        log.warning("payload has non-string required fields: %s", sorted(wrong_type))
        return False
    return True
