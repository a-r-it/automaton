"""Per-task model-tier routing for Agent dispatches -- warden port of the
bash pre-agent-model-routing hook, decision order preserved. Dormant unless
the project (or HOME) has .automaton/development/model-routing.json. Reads
in_progress tasks from the transcript via the shared hooks/lib/task_model
(hooks cannot call TaskGet). Registered in registry.py under "Agent";
hooks.json scopes the matcher to feature-development sessions."""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "lib"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "lib"))  # shared task_model
from hook_common import NO_TASK, TRACE_LOG, Context  # noqa: E402
from plugin_contract import DispatchRole, EnvVar, RuleName, TraceEvent  # noqa: E402
from task_model import fence_meta, reconstruct  # noqa: E402

NAME = RuleName.MODEL_ROUTING

ROUTING_RELPATH = os.path.join(".automaton", "development", "model-routing.json")
GENERAL_PURPOSE = "general-purpose"
REVIEWER_TIER = "standard"
INHERIT = "inherit"


def _routing_file(cwd: str) -> tuple[str, str] | None:
    """(path, display label) of the first routing file found: project cwd
    first, then HOME; first found wins entirely, no merging."""
    base = cwd or os.getcwd()
    candidates = (
        (os.path.join(base, ROUTING_RELPATH), ROUTING_RELPATH),
        (os.path.join(os.path.expanduser("~"), ROUTING_RELPATH),
         "~/" + ROUTING_RELPATH),
    )
    for path, label in candidates:
        if os.path.isfile(path):
            return path, label
    return None


def check(ctx: Context) -> str | None:
    agent = ctx.payload.agent_input()

    role = agent.subagent_type
    if role == DispatchRole.CODE_REVIEWER:
        ctx.trace(NO_TASK, TraceEvent.PASS, "code-reviewer-exempt")
        return None
    if role and role != GENERAL_PURPOSE and role not in (
            DispatchRole.IMPLEMENTER, DispatchRole.TASK_REVIEWER):
        ctx.trace(NO_TASK, TraceEvent.PASS,
                  f"custom-agent-type-exempt type={role}")
        return None

    found = _routing_file(ctx.payload.cwd)
    if found is None:
        ctx.trace(NO_TASK, TraceEvent.PASS, "no-routing-file")
        return None
    path, label = found
    try:
        with open(path) as f:
            routing = json.load(f)
    except Exception:
        ctx.trace(NO_TASK, TraceEvent.PASS, "routing-file-unparseable")
        return None
    if not isinstance(routing, dict):
        ctx.trace(NO_TASK, TraceEvent.PASS, "routing-file-not-object")
        return None

    if role == DispatchRole.TASK_REVIEWER:
        return _check_task_reviewer(ctx, routing, agent.model, label)
    if role == DispatchRole.IMPLEMENTER:
        return _check_implementer(ctx, routing, agent.model, label)

    transcript = ctx.payload.transcript_path
    if not transcript or not os.path.isfile(transcript):
        ctx.trace(NO_TASK, TraceEvent.PASS, "no-transcript")
        return None

    tasks, inprogress = reconstruct(transcript)
    task_id = inprogress[-1] if inprogress else "?"
    subject = tasks.get(task_id, {}).get("subject", "") if inprogress else ""

    # Union over ALL in_progress tasks: bounded parallel dispatch means a
    # dispatch may serve any of them.
    tiers: list[str] = []
    has_pin = False
    for tid in inprogress:
        meta = fence_meta(tasks.get(tid, {}).get("description", ""))
        if meta.get("model"):
            has_pin = True
        tier = meta.get("modelTier")
        if isinstance(tier, str) and tier and tier not in tiers:
            tiers.append(tier)
    tiers_display = ",".join(tiers)

    if not has_pin and not tiers:
        ctx.trace(task_id, TraceEvent.PASS, "no-tier-requirement")
        return None
    # Any in_progress task with a concrete model pin -> defer entirely: pin
    # enforcement belongs to the (dormant) dispatch-validate hook, and
    # double-blocking one dispatch from two gates would deadlock.
    if has_pin:
        ctx.trace(task_id, TraceEvent.PASS, "pin-owned-by-dispatch-validate")
        return None

    ctx.trace(task_id, TraceEvent.ENTER, f"tiers={tiers_display}")

    allowed: list[str] = []
    for tier in tiers:
        resolved = routing.get(tier)
        # Unknown tier member -> drop it (fail-open per member; a typo must
        # not brick dispatches for the whole union).
        if not isinstance(resolved, str) or not resolved:
            continue
        # Any member resolving to "inherit" -> no constraint at all.
        if resolved == INHERIT:
            ctx.trace(task_id, TraceEvent.PASS,
                      f"tier-inherit tiers={tiers_display}")
            return None
        if resolved not in allowed:
            allowed.append(resolved)

    # Every tier was unknown to the routing file -> fail open.
    if not allowed:
        ctx.trace(task_id, TraceEvent.PASS,
                  f"unknown-tier-failopen tiers={tiers_display}")
        return None

    standard = routing.get(REVIEWER_TIER)
    standard = standard if isinstance(standard, str) else ""
    # "standard" -> "inherit" makes the reviewer member a wildcard: allow any.
    if standard == INHERIT:
        ctx.trace(task_id, TraceEvent.PASS,
                  f"standard-inherit-wildcard tiers={tiers_display}")
        return None
    if standard and standard not in allowed:
        allowed.append(standard)

    if agent.model and agent.model in allowed:
        ctx.trace(task_id, TraceEvent.PASS,
                  f"tier-match tiers={tiers_display} model={agent.model}")
        return None

    ctx.trace(task_id, TraceEvent.BLOCK,
              f"tier-mismatch tiers={tiers_display} "
              f"allowed={' '.join(allowed)} got={agent.model}")
    return _block_message(task_id, subject, tiers_display, allowed,
                          standard, agent.model, label)


def _check_task_reviewer(ctx: Context, routing: dict[str, object], model: str,
                         label: str) -> str | None:
    """Decision 11: task-reviewer = standard-tier model OR omitted
    (omitting is the Decision 14 reviewer escalation)."""
    standard = routing.get(REVIEWER_TIER)
    if not isinstance(standard, str) or not standard or standard == INHERIT:
        ctx.trace(NO_TASK, TraceEvent.PASS, "reviewer-standard-unconstrained")
        return None
    if not model or model == standard:
        ctx.trace(NO_TASK, TraceEvent.PASS,
                  f"reviewer-ok model={model or '(omitted)'}")
        return None
    ctx.trace(NO_TASK, TraceEvent.BLOCK,
              f"reviewer-mismatch want={standard} got={model}")
    return _role_block_message(
        "task-reviewer", f"'{standard}' (or omit the model param to "
        "escalate to the session model)", model, label)


def _check_implementer(ctx: Context, routing: dict[str, object], model: str,
                       label: str) -> str | None:
    """Decision 11: implementer/fixer = exactly the in-progress task's tier
    model; absent/invalid tier resolves to 'standard'; tier 'inherit' means
    the model param must be omitted."""
    transcript = ctx.payload.transcript_path
    if not transcript or not os.path.isfile(transcript):
        ctx.trace(NO_TASK, TraceEvent.PASS, "no-transcript")
        return None
    tasks, inprogress = reconstruct(transcript)
    if not inprogress:
        ctx.trace(NO_TASK, TraceEvent.PASS, "implementer-no-inprogress")
        return None
    task_id = inprogress[-1]
    meta = fence_meta(tasks.get(task_id, {}).get("description", ""))
    if meta.get("model"):
        ctx.trace(task_id, TraceEvent.PASS, "pin-owned-by-dispatch-validate")
        return None
    tier = meta.get("modelTier")
    if not isinstance(tier, str) or tier not in routing:
        tier = REVIEWER_TIER  # absent/invalid tier -> standard (Decision 11)
    resolved = routing.get(tier)
    if not isinstance(resolved, str) or not resolved:
        ctx.trace(task_id, TraceEvent.PASS, f"tier-unmapped tier={tier}")
        return None
    if resolved == INHERIT:
        if not model:
            ctx.trace(task_id, TraceEvent.PASS, f"tier-inherit tier={tier}")
            return None
        ctx.trace(task_id, TraceEvent.BLOCK,
                  f"inherit-requires-omitted tier={tier} got={model}")
        return _role_block_message(
            "implementer", "no model param at all (the task's tier resolves "
            "to 'inherit' = session model)", model, label)
    if model == resolved:
        ctx.trace(task_id, TraceEvent.PASS,
                  f"tier-match tier={tier} model={model}")
        return None
    ctx.trace(task_id, TraceEvent.BLOCK,
              f"tier-mismatch tier={tier} want={resolved} "
              f"got={model or '(none)'}")
    return _role_block_message(
        "implementer", f"exactly '{resolved}' (task #{task_id} tier "
        f"'{tier}')", model, label)


def _role_block_message(role: str, want: str, got_model: str,
                        label: str) -> str:
    got_display = got_model or "(none)"
    return f"""FEATURE-DEVELOPMENT DISPATCH DOES NOT MATCH ITS ROLE'S MODEL RULE

A development:{role} dispatch must use {want}.
Your Agent call passed model='{got_display}'. Active routing file: {label}.

Role rules (design Decision 11):
  - implementer / fix dispatches -> exactly the in-progress task's tier model
    ('inherit' tier = omit the param); escalate a tier via the Decision 14
    protocol (update the task fence + tasks.json + manifest FIRST)
  - task-reviewer -> the 'standard' tier model, or omit to escalate
  - code-reviewer -> always omits; never blocked

(Runtime disable: {EnvVar.WARDEN}=0. Trace log: {TRACE_LOG})"""


def _block_message(task_id: str, subject: str, tiers_display: str,
                   allowed: list[str], standard: str, got_model: str,
                   label: str) -> str:
    standard_display = standard or "(tier 'standard' not mapped in routing file)"
    got_display = got_model or "(none)"
    allowed_display = " ".join(allowed)
    return f"""AGENT DISPATCH DOES NOT MATCH TASK MODEL TIER

Task #{task_id} ('{subject}') is the most recent of the in_progress
tasks (tiers in progress: {tiers_display}). The active routing file
({label}) resolves those to model '{allowed[0]}'
(full allowed set: {allowed_display}). Your Agent call passed model='{got_display}'.

Allowed per {label}:
  - implementer / fix dispatches -> the model of the task they serve (allowed set above)
  - spec & code-quality reviewers -> model: {standard_display}
  - final whole-plan reviewer (runs after all tasks complete) -> no in_progress task, this gate won't fire

Options:
  1. Re-issue the Agent call with the model matching the task this
     dispatch serves -- one of: {allowed_display} (the plan tiered these
     tasks for cost reasons).
  2. If this dispatch is genuinely not work for any in_progress task
     (unrelated helper call), or a tier is wrong, update that task's
     metadata via TaskUpdate transparently, then retry.
  3. Escalate to the user via AskUserQuestion if you believe the routing
     mapping itself is wrong.

Tier rules: README.md, Subagent Model Routing
(Runtime disable: {EnvVar.WARDEN}=0. Trace log: {TRACE_LOG})"""
