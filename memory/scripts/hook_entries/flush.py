"""
Memory flush agent - extracts important knowledge from conversation context.

Spawned by session-end.py or pre-compact.py as a background process. Reads
pre-extracted conversation context from a .md file, uses the Claude Agent SDK
to decide what's worth saving, and appends the result to today's daily log.

Usage:
    uv run python flush.py <context_file.md> <session_id>
"""

from __future__ import annotations

# Recursion prevention: set this BEFORE any imports that might trigger Claude
import os
import sys
from pathlib import Path

from scripts.core.constants import (
    COMPILE_LOG_FILENAME,
    ENV_CLAUDE_INVOKED_BY,
    ENV_FLUSH_STDERR_LOG,
    FLUSH_LOG_FILENAME,
    INVOKED_BY_FLUSH,
    LAST_FLUSH_FILENAME,
    STATE_FILENAME,
)

os.environ[ENV_CLAUDE_INVOKED_BY] = INVOKED_BY_FLUSH

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from scripts.core.agent import ANALYSIS_OPTIONS, run_agent
from scripts.core.cli import CliContextP, cli_main
from scripts.core.errors import AgentError
from scripts.core.exit_codes import ExitCode
from scripts.core.redact import redact
from scripts.prompts import build_flush

if TYPE_CHECKING:
    from scripts.core.config import Config

log = logging.getLogger(__name__)


def load_flush_state(config: Config) -> dict[str, Any]:
    state_file = config.wiki / LAST_FLUSH_FILENAME
    if state_file.exists():
        try:
            data: dict[str, Any] = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        else:
            return data
    return {}


def save_flush_state(config: Config, state: dict[str, Any]) -> None:
    state_file = config.wiki / LAST_FLUSH_FILENAME
    state_file.write_text(json.dumps(state), encoding="utf-8")


def append_to_daily_log(
    config: Config, content: str, *, section: str = "Session", truncated: bool = False
) -> None:
    """Append content to today's daily log.

    When truncated=True and section == "Session", prepend a
    ``**Truncated:** true`` line before the content body. The marker is
    ignored for service sections (``Memory Flush``) so FLUSH_OK / FLUSH_ERROR
    rows stay clean.
    """
    cfg = config
    today = datetime.now(UTC).astimezone()
    log_path = cfg.daily / f"{today.strftime('%Y-%m-%d')}.md"

    if not log_path.exists():
        cfg.daily.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"# Daily Log: {today.strftime('%Y-%m-%d')}\n\n## Sessions\n\n## Memory Maintenance\n\n",
            encoding="utf-8",
        )

    time_str = today.strftime("%H:%M")
    if truncated and section == "Session":
        content = f"**Truncated:** true\n\n{content}"
    entry = f"### {section} ({time_str})\n\n{content}\n\n"

    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)


async def run_flush(config: Config, context: str) -> str:
    """Use Claude Agent SDK to extract important knowledge from conversation context."""
    prompt = build_flush(context=context)

    response = ""
    try:
        result = await run_agent(prompt, cwd=config.compiler_root, options=ANALYSIS_OPTIONS)
        response = result.text
    except Exception as e:
        log.exception("Agent SDK error: %s", type(e).__name__)
        response = f"FLUSH_ERROR: {type(e).__name__}: {e}"

    return response


def maybe_trigger_compilation(config: Config) -> None:
    """If it's past the compile hour and today's log hasn't been compiled, run compile.py."""
    import subprocess as _sp

    cfg = config
    now = datetime.now(UTC).astimezone()
    if now.hour < cfg.compile_after_hour:
        return

    # Check if today's log has already been compiled
    today_log = f"{now.strftime('%Y-%m-%d')}.md"
    compile_state_file = cfg.wiki / STATE_FILENAME
    if compile_state_file.exists():
        try:
            compile_state = json.loads(compile_state_file.read_text(encoding="utf-8"))
            ingested = compile_state.get("ingested", {})
            if today_log in ingested:
                # Already compiled today - check if the log has changed since
                from hashlib import sha256

                log_path = cfg.daily / today_log
                if log_path.exists():
                    current_hash = sha256(log_path.read_bytes()).hexdigest()[:16]
                    if ingested[today_log].get("hash") == current_hash:
                        return  # log unchanged since last compile
        except (json.JSONDecodeError, OSError):
            pass

    compile_script = cfg.scripts / "compile.py"
    if not compile_script.exists():
        return

    log.info("End-of-day compilation triggered (after %d:00)", cfg.compile_after_hour)

    cmd = ["uv", "run", "--directory", str(cfg.compiler_root), "python", str(compile_script)]

    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            _sp.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | _sp.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True

    try:
        with (cfg.wiki / COMPILE_LOG_FILENAME).open("a") as log_handle:
            _sp.Popen(
                cmd, stdout=log_handle, stderr=_sp.STDOUT, cwd=str(cfg.compiler_root), **kwargs
            )
    except Exception as e:
        log.exception("Failed to spawn compile.py: %s", type(e).__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract important knowledge from a conversation context file"
    )
    parser.add_argument("context_file", type=str, help="Path to the pre-extracted context .md file")
    parser.add_argument("session_id", type=str, help="Session identifier (for dedup)")
    parser.add_argument(
        "--truncated",
        action="store_true",
        help="Mark the resulting Session entry as truncated (PreCompact path)",
    )
    return parser


async def _run_flush(args: argparse.Namespace, config: Config) -> None:  # noqa: C901  # inherent: 3 early-return guards + response dispatch; extracting needs 4+ params
    # Set up file-based logging so we can verify the background process ran.
    # The parent process sends stdout/stderr to DEVNULL (to avoid the inherited
    # file handle bug on Windows), so this is our only observability channel.
    # Done here (not at module level) so importing flush.py without WIKI_ROOT is safe.
    log_file = config.wiki / FLUSH_LOG_FILENAME
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    context_file = Path(args.context_file)
    session_id: str = args.session_id
    truncated: bool = args.truncated

    # Optional per-session stderr log path set by flush_common.py. Unset when
    # flush.py is invoked manually outside of a hook — in that case we skip
    # stderr-related cleanup / logging.
    stderr_path_str = os.environ.get(ENV_FLUSH_STDERR_LOG)
    stderr_path: Path | None = Path(stderr_path_str) if stderr_path_str else None

    log.info(
        "flush.py started for session %s, context: %s, truncated=%s",
        session_id,
        context_file,
        truncated,
    )

    def _cleanup_artifacts() -> None:
        """Remove context and stderr files. Used by early-return skip paths."""
        context_file.unlink(missing_ok=True)
        if stderr_path is not None:
            stderr_path.unlink(missing_ok=True)

    if not context_file.exists():  # noqa: ASYNC240  # CLI tool; local I/O is negligible vs. LLM call
        log.error("Context file not found: %s", context_file)
        _cleanup_artifacts()
        return

    state = load_flush_state(config)
    if state.get("session_id") == session_id and time.time() - state.get("timestamp", 0) < 60:
        log.info("Skipping duplicate flush for session %s", session_id)
        _cleanup_artifacts()
        return

    context = context_file.read_text(encoding="utf-8").strip()  # noqa: ASYNC240  # CLI tool; local I/O is negligible vs. LLM call
    if not context:
        log.info("Context file is empty, skipping")
        _cleanup_artifacts()
        return

    log.info("Flushing session %s: %d chars", session_id, len(context))

    response = await run_flush(config, context)

    response, _redact_notices = redact(response)
    for _notice in _redact_notices:
        log.warning("REDACTED: %s", _notice)

    if "FLUSH_OK" in response:
        log.info("Result: FLUSH_OK")
        append_to_daily_log(
            config, "FLUSH_OK - Nothing worth saving from this session", section="Memory Flush"
        )
    elif "FLUSH_ERROR" in response:
        log.error(
            "Result: %s; stderr: %s; context: %s",
            response,
            stderr_path,
            context_file,
        )
        append_to_daily_log(config, response, section="Memory Flush")
    else:
        log.info("Result: saved to daily log (%d chars)", len(response))
        append_to_daily_log(config, response, section="Session", truncated=truncated)

    save_flush_state(config, {"session_id": session_id, "timestamp": time.time()})

    if "FLUSH_ERROR" not in response:
        context_file.unlink(missing_ok=True)  # noqa: ASYNC240  # CLI tool; local I/O is negligible vs. LLM call
        if stderr_path is not None:
            stderr_path.unlink(missing_ok=True)  # noqa: ASYNC240  # CLI tool; local I/O is negligible vs. LLM call

    maybe_trigger_compilation(config)

    log.info("Flush complete for session %s", session_id)


@cli_main(name="flush", parser_factory=build_parser)
async def main(ctx: CliContextP) -> ExitCode:
    try:
        await _run_flush(ctx.args, ctx.config)
    except Exception as exc:
        raise AgentError(stage="flush-run", underlying=str(exc)) from exc
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
