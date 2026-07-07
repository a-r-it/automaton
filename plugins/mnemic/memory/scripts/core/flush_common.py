"""Shared helpers for pre-compact and session-end hooks.

Both hooks read a Claude Code JSONL transcript, extract the tail, and spawn
flush.py in the background. Kept in a shared module so the two hooks stay
in sync; differences live in each hook's call site (min-turns threshold and
context-file prefix).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal

from scripts.core.constants import ENV_FLUSH_STDERR_LOG

if TYPE_CHECKING:
    import logging
    from collections.abc import Iterator

    from scripts.core.hook_types import HookStdinPayload

MAX_TURNS = 30
MAX_CONTEXT_CHARS = 15_000


@contextlib.contextmanager
def _open_stderr_sink(
    path: Path, logger: logging.Logger
) -> Iterator[tuple[IO[str] | int, str | None]]:
    """Yield (handle, path_str) for subprocess stderr; fall back to DEVNULL on OSError."""
    try:
        with path.open("w") as handle:
            yield handle, str(path)
    except OSError as e:
        logger.warning("Failed to open stderr log %s: %s; falling back to DEVNULL", path, e)
        yield subprocess.DEVNULL, None


def extract_conversation_context(transcript_path: Path) -> tuple[str, int]:  # noqa: C901, PLR0912  # inherent: JSONL parser handles content-shape variants (dict/list/str)
    """Read JSONL transcript and extract last ~N conversation turns as markdown."""
    turns: list[str] = []

    with transcript_path.open(encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("message", {})
            if isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
            else:
                role = entry.get("role", "")
                content = entry.get("content", "")

            if role not in ("user", "assistant"):
                continue

            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts)

            if isinstance(content, str) and content.strip():
                label = "User" if role == "user" else "Assistant"
                turns.append(f"**{label}:** {content.strip()}\n")

    recent = turns[-MAX_TURNS:]
    context = "\n".join(recent)

    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
        boundary = context.find("\n**")
        if boundary > 0:
            context = context[boundary + 1 :]

    return context, len(recent)


def run_flush_hook(
    *,
    event_name: Literal["PreCompact", "SessionEnd"],
    payload: HookStdinPayload,
    logger: logging.Logger,
    min_turns: int,
    file_prefix: str,
    state_dir: Path,
    compiler_root: Path,
    truncated: bool = False,
) -> None:
    """End-to-end hook body shared by pre-compact and session-end.

    Takes a typed ``payload`` (already parsed and validated by
    ``core.hook_types.parse_hook_input``) and a ``logger`` (per-event
    named logger configured by the entrypoint). Extracts the transcript
    tail, writes a context file into ``state_dir``, and spawns
    ``flush.py`` in the background.

    ``truncated=True`` appends ``--truncated`` to the scripts.hook_entries.flush command so the
    daily-log entry it writes carries a ``**Truncated:** true`` marker.
    """
    session_id = payload["session_id"]
    transcript_path_str = payload["transcript_path"]

    logger.info(
        "%s fired: session=%s reason=%s",
        event_name,
        session_id,
        payload["reason"],
    )

    if not transcript_path_str:
        logger.info("SKIP: no transcript path")
        return

    transcript_path = Path(transcript_path_str)
    if not transcript_path.exists():
        logger.info("SKIP: transcript missing: %s", transcript_path_str)
        return

    try:
        context, turn_count = extract_conversation_context(transcript_path)
    except Exception as e:
        logger.exception("Context extraction failed: %s", type(e).__name__)
        return

    if not context.strip():
        logger.info("SKIP: empty context")
        return

    if turn_count < min_turns:
        logger.info("SKIP: only %d turns (min %d)", turn_count, min_turns)
        return

    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
    context_file = state_dir / f"{file_prefix}-{session_id}-{timestamp}.md"
    context_file.write_text(context, encoding="utf-8")

    stderr_file = state_dir / f"flush-stderr-{session_id}-{timestamp}.log"

    cmd = [
        "uv",
        "run",
        "--directory",
        str(compiler_root),
        "python",
        "-m",
        "scripts.hook_entries.flush",
        str(context_file),
        session_id,
    ]
    if truncated:
        cmd.append("--truncated")
    creation_flags = (
        subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        if sys.platform == "win32"
        else 0
    )

    with _open_stderr_sink(stderr_file, logger) as (stderr_handle, stderr_path_str):
        child_env = os.environ.copy()
        if stderr_path_str is not None:
            child_env[ENV_FLUSH_STDERR_LOG] = stderr_path_str

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                env=child_env,
                creationflags=creation_flags,
            )
            logger.info(
                "Spawned scripts.hook_entries.flush for session %s (%d turns, %d chars) PID=%s stderr→%s",
                session_id,
                turn_count,
                len(context),
                proc.pid,
                stderr_path_str or "DEVNULL",
            )
        except Exception as e:
            logger.exception("Failed to spawn scripts.hook_entries.flush: %s", type(e).__name__)
