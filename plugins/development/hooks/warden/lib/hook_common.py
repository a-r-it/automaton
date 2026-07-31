"""Shared runtime for warden: payload read, trace writer, block emitter,
per-rule Context. Pass/skip/fail-open are SILENT (exit 0, no stdout) -- a
PreToolUse hook that emits nothing defers to the normal permission flow.
Rules veto only (exit 2 + stderr). permissionDecision "allow" is banned:
a hook with no veto to cast has no business granting permission."""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, NoReturn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contracts import HookPayload  # noqa: E402
from plugin_contract import DefaultPath, EnvVar  # noqa: E402

TRACE_LOG = os.environ.get(EnvVar.TRACE_LOG, str(DefaultPath.TRACE_LOG))

# Trace-line placeholder when no concrete task applies.
NO_TASK = "-"


def read_payload() -> Any:
    return json.load(sys.stdin)


def trace_writer(hook_name: str) -> Callable[..., None]:
    """trace(task_id, event, reason="") ->
    'TS | <hook_name> | task=ID | event | reason' (reason optional)."""

    def trace(*args: str) -> None:
        try:
            os.makedirs(os.path.dirname(TRACE_LOG), exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            task_id, event = args[0], args[1]
            reason = args[2] if len(args) > 2 else ""
            body = f"task={task_id} | {event}"
            if reason:
                body += f" | {reason}"
            with open(TRACE_LOG, "a") as f:
                f.write(f"{ts} | {hook_name} | {body}\n")
        except Exception:
            pass

    return trace


def emit_block(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(2)


def _noop_trace(*args: str) -> None:
    return None


class Context:
    """What a rule's check(ctx) receives: typed envelope + rule-bound trace
    (the runner rebinds before each rule)."""

    __slots__ = ("payload", "trace")

    def __init__(self, payload: HookPayload,
                 trace: Callable[..., None] | None = None) -> None:
        self.payload = payload
        self.trace: Callable[..., None] = trace or _noop_trace
