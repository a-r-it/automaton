"""The per-rule loop, extracted for unit testing: lazy import + isolation.
Rule module contract: NAME (trace name) + check(ctx) -> str | None."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from hook_common import NO_TASK, Context, trace_writer
from plugin_contract import TRACE_TRAP_ERR, TraceEvent


def run_rules(
    ctx: Context,
    rule_names: Sequence[str],
    import_rule: Callable[[str], Any],
    runner_trace: Callable[..., None],
) -> str | None:
    """First veto's message, or None. A rule that fails to import or raises
    is traced and skipped -- the blast radius is that one rule, never the
    engine."""
    for name in rule_names:
        try:
            rule = import_rule(name)
        except Exception as exc:
            runner_trace(NO_TASK, TraceEvent.SKIP,
                         f"{TRACE_TRAP_ERR}:import:{name}:{exc.__class__.__name__}")
            continue
        try:
            ctx.trace = trace_writer(rule.NAME)
            message: str | None = rule.check(ctx)
        except Exception as exc:
            rule_name = getattr(rule, "NAME", name)
            runner_trace(NO_TASK, TraceEvent.SKIP,
                         f"{TRACE_TRAP_ERR}:{rule_name}:{exc.__class__.__name__}")
            continue
        if message is not None:
            return message
    return None
