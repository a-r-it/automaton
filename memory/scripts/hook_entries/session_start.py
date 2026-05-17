"""SessionStart hook — injects knowledge base context into every conversation.

This is the "context injection" layer. When Claude Code starts a session,
this hook reads the knowledge base index and recent daily log, then injects
them as additional context so Claude always "remembers" what it has learned.

Configure in ``hooks/hooks.json`` (plugin-shipped); installation toggles
the per-project ``.automaton/config.toml`` enabled flag.

NOTE: session-start is the ONE entrypoint exempted from the default
bubble-everything uncaught-exception policy. The SessionStart hook
expects JSON on stdout; a traceback would poison the user's next
session. Do NOT copy the ``try / except Exception:`` pattern in
``main()`` to other hooks.

Module-level imports deliberately AVOID importing from ``config`` (the
PEP 562 shim) — that would trigger ``load_config()`` at import time,
which requires ``WIKI_ROOT``. Resolved paths are read from ``ctx.config``
inside ``main()`` instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from scripts.core.cli import CliContextP, cli_main
from scripts.core.exit_codes import ExitCode
from scripts.core.hook_preflight import opt_in_or_exit

if TYPE_CHECKING:
    from pathlib import Path

MAX_CONTEXT_CHARS = 20_000
MAX_LOG_LINES = 30


def _get_recent_log(daily_dir: Path) -> str:
    """Read the most recent daily log (today or yesterday)."""
    today = datetime.now(UTC).astimezone()

    for offset in range(2):
        date = today - timedelta(days=offset)
        log_path = daily_dir / f"{date.strftime('%Y-%m-%d')}.md"
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").splitlines()
            recent = lines[-MAX_LOG_LINES:] if len(lines) > MAX_LOG_LINES else lines
            return "\n".join(recent)

    return "(no recent daily log)"


def _build_context(daily_dir: Path, index_file: Path) -> str:
    """Assemble the context to inject into the conversation."""
    parts: list[str] = []

    today = datetime.now(UTC).astimezone()
    parts.append(f"## Today\n{today.strftime('%A, %B %d, %Y')}")

    if index_file.exists():
        index_content = index_file.read_text(encoding="utf-8")
        parts.append(f"## Knowledge Base Index\n\n{index_content}")
    else:
        parts.append("## Knowledge Base Index\n\n(empty - no articles compiled yet)")

    recent_log = _get_recent_log(daily_dir)
    parts.append(f"## Recent Daily Log\n\n{recent_log}")

    context = "\n\n---\n\n".join(parts)

    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n\n...(truncated)"

    return context


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="SessionStart hook entrypoint")


@cli_main(name="session-start", parser_factory=build_parser)
def main(ctx: CliContextP) -> ExitCode:
    # Fail-open exemption: a crash here would emit a traceback on stdout
    # and poison every downstream session that wires this hook. Never
    # propagate. See module-level NOTE for why this is the only
    # entrypoint allowed to swallow Exception.
    try:
        context = _build_context(ctx.config.daily, ctx.config.index_file)
    except Exception as exc:  # noqa: BLE001  # see fail-open NOTE above
        ctx.log.warning(
            "session-start suppressed uncaught exception: %s",
            exc,
            exc_info=True,
        )
        context = ""

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        },
    }
    print(json.dumps(output))
    return ExitCode.OK


if __name__ == "__main__":
    opt_in_or_exit()
    sys.exit(main())
