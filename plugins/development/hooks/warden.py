"""Single entrypoint for warden -- the development plugin's hook engine.

hooks.json invokes `python3 hooks/warden.py --agents <a,b,c>` on every
registered matcher. Sequence: DEVELOPMENT_WARDEN kill switch (stdlib-only
prologue: before stdin, before any warden import) -> hand-rolled argv parse
(argparse is banned -- its SystemExit(2) would veto) -> stdin -> payload ->
event dispatch by hook_event_name (only PreToolUse today) -> agent-scope
gate (--agents aliases; main session has no alias and always passes open)
-> matching rules imported lazily, one at a time. First veto wins (exit 2 +
stderr); every non-veto outcome is silent exit 0 -- warden NEVER emits
permissionDecision "allow". Layered fail-open: malformed argv, unparseable
stdin, an unknown alias, a broken rule import, or a raising rule is traced
and the event passes open; emit_block sits outside every try so a real veto
can never be swallowed."""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True

# Kill switch. The literal (not EnvVar.WARDEN) is deliberate: nothing may be
# imported before this line. Pinned to the enum by test_warden.py.
if os.environ.get("DEVELOPMENT_WARDEN", "1") == "0":
    sys.exit(0)

_HERE = os.path.dirname(os.path.abspath(__file__))
for _d in ("warden", os.path.join("warden", "lib"),
           os.path.join("warden", "rules"), "lib"):
    sys.path.insert(0, os.path.join(_HERE, _d))


def _parse_agents(argv: list[str]) -> list[str] | None:
    """['--agents', 'a,b'] -> ['a', 'b']; None on any other shape."""
    if len(argv) != 2 or argv[0] != "--agents":
        return None
    aliases = [a.strip() for a in argv[1].split(",") if a.strip()]
    return aliases or None


def run() -> None:
    try:
        import importlib

        import registry
        from cc_contract import HookEvent
        from contracts import HookPayload
        from hook_common import Context, emit_block, read_payload, trace_writer
        from hook_common import NO_TASK
        from plugin_contract import (
            TRACE_TRAP_ERR,
            AgentType,
            RuleName,
            TraceEvent,
            TraceReason,
        )
        from runner import run_rules
    except Exception:
        return  # engine's own lib is broken: fail open (nowhere to trace yet)

    runner_trace = trace_writer(RuleName.WARDEN)

    aliases = _parse_agents(sys.argv[1:])
    if aliases is None:
        runner_trace(NO_TASK, TraceEvent.SKIP, TraceReason.BAD_ARGV)
        return

    try:
        payload = HookPayload.from_dict(read_payload())
    except Exception:
        runner_trace(NO_TASK, TraceEvent.SKIP,
                     f"{TRACE_TRAP_ERR}:unparseable-stdin")
        return
    if payload.problems:
        runner_trace(NO_TASK, TraceEvent.ENTER,
                     "problems: " + "; ".join(payload.problems))

    if payload.hook_event_name != HookEvent.PRE_TOOL_USE:
        runner_trace(NO_TASK, TraceEvent.SKIP,
                     f"{TraceReason.UNHANDLED_EVENT}:"
                     f"{payload.hook_event_name or '?'}")
        return

    scoped: set[str] = set()
    for alias in aliases:
        agent = AgentType.from_alias(alias)
        if agent is None:
            runner_trace(NO_TASK, TraceEvent.SKIP,
                         f"{TraceReason.UNKNOWN_ALIAS}:{alias}")
            continue
        scoped.add(str(agent))

    agent_type = (payload.agent_type or "").strip()
    if agent_type not in scoped:
        # Deliberate trace: records the wire agent_type string -- this is how
        # sandbox verification (and future debugging) reads what the harness
        # actually sends.
        runner_trace(NO_TASK, TraceEvent.SKIP,
                     f"{TraceReason.OUT_OF_SCOPE}:{agent_type or 'main'}")
        return

    message = run_rules(
        Context(payload),
        registry.rules_for(payload.tool_name),
        importlib.import_module,
        runner_trace,
    )
    if message is not None:
        emit_block(message)


if __name__ == "__main__":
    run()
