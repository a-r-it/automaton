"""PreCompact hook — captures conversation transcript before auto-compaction.

When Claude Code's context window fills up, it auto-compacts (summarises
and discards detail). This hook fires BEFORE that happens, extracting
conversation context and spawning ``flush.py`` to extract knowledge that
would otherwise be lost to summarisation.

The hook itself does NO API calls — only local file I/O for speed (<10s).

Marker / recursion guard: the ``__main__`` guard calls
``opt_in_or_exit()`` BEFORE ``main()``. ``main()`` is callable from tests
unconditionally; in production it only runs when the project has opted
in to automation.

Module-level imports deliberately AVOID importing from ``config`` (the
PEP 562 shim) — that would trigger ``load_config()`` at import time,
which requires ``WIKI_ROOT``. Resolved paths are read from ``ctx.config``
inside ``main()`` instead.
"""

from __future__ import annotations

import argparse
import sys

from scripts.core.cli import CliContextP, cli_main
from scripts.core.constants import FLUSH_LOG_FILENAME
from scripts.core.exit_codes import ExitCode
from scripts.core.flush_common import (  # noqa: F401  (re-export for tests)
    extract_conversation_context,
    run_flush_hook,
)
from scripts.core.hook_preflight import opt_in_or_exit
from scripts.core.hook_types import parse_hook_input
from scripts.core.logging import resolve_log_mode, setup_logger

MIN_TURNS_TO_FLUSH = 5


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="PreCompact hook entrypoint")


@cli_main(name="pre-compact", parser_factory=build_parser)
def main(ctx: CliContextP) -> ExitCode:
    flush_log_path = ctx.config.wiki / FLUSH_LOG_FILENAME
    log_mode = resolve_log_mode(for_file=True)
    # Configure the "flush" logger that core.hook_types.parse_hook_input
    # uses for parser diagnostics (AC#9 — invalid stdin must land an
    # ERROR record in flush.log, not just stderr-via-lastResort).
    setup_logger("flush", mode=log_mode, log_file=flush_log_path)
    log = setup_logger(
        "pre-compact",
        mode=log_mode,
        log_file=flush_log_path,
    )
    payload = parse_hook_input("PreCompact")
    if payload is None:
        return ExitCode.OK  # invalid stdin → fail-open silent
    run_flush_hook(
        event_name="PreCompact",
        payload=payload,
        logger=log,
        min_turns=MIN_TURNS_TO_FLUSH,
        file_prefix="flush-context",
        state_dir=ctx.config.wiki,
        compiler_root=ctx.config.compiler_root,
        truncated=True,
    )
    return ExitCode.OK


if __name__ == "__main__":
    opt_in_or_exit()
    sys.exit(main())
