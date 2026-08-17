"""Per-event rule slices for warden. PRE_TOOL_USE maps tool name -> ordered
rule module names; registry order is decision order (first veto wins).
Adding a rule for an already-matched tool = module in rules/ + a line here
(modules are re-read every invocation, no reinstall); a NEW tool or cohort
also needs its hooks.json registration + plugin reload."""
from __future__ import annotations

PRE_TOOL_USE: dict[str, tuple[str, ...]] = {
    "EnterPlanMode": ("planmode_ban",),
}


def rules_for(tool_name: str) -> tuple[str, ...]:
    return PRE_TOOL_USE.get(tool_name, ())
