"""Vocabulary for warden's OWN protocol -- every machine-readable string this
layer invented, declared once. StrEnum values are byte-identical to the
protocol strings (pinned by test_contracts.py)."""
from __future__ import annotations

from enum import StrEnum

TRACE_TRAP_ERR = "trap-ERR"


class AgentType(StrEnum):
    """Wire agent_type strings, keyed by the --agents aliases in hooks.json.
    ARCHITECT's value is the sandbox-verification target (plan Task 5)."""

    ARCHITECT = "development:architect"
    FEATURE_DEVELOPMENT = "development:feature-development"

    @classmethod
    def from_alias(cls, alias: str) -> AgentType | None:
        return _ALIASES.get(alias)


_ALIASES: dict[str, AgentType] = {
    "architect": AgentType.ARCHITECT,
    "feature-development": AgentType.FEATURE_DEVELOPMENT,
}


class DispatchRole(StrEnum):
    """Wire subagent_type strings of the feature-development worker agents; the
    model_routing rule keys role-aware enforcement on them."""

    IMPLEMENTER = "development:implementer"
    TASK_REVIEWER = "development:task-reviewer"
    CODE_REVIEWER = "development:code-reviewer"


class EnvVar(StrEnum):
    WARDEN = "DEVELOPMENT_WARDEN"
    TRACE_LOG = "DEVELOPMENT_WARDEN_TRACE_LOG"


class DefaultPath(StrEnum):
    TRACE_LOG = "/tmp/claude-hooks/user-gate-trace.log"


class RuleName(StrEnum):
    WARDEN = "warden"  # the runner's trace name, not a rule
    PLANMODE_BAN = "warden:planmode-ban"
    MODEL_ROUTING = "warden:model-routing"


class TraceEvent(StrEnum):
    PASS = "pass"
    BLOCK = "block"
    SKIP = "skip"
    ENTER = "enter"


class TraceReason(StrEnum):
    BAD_ARGV = "bad-argv"
    UNKNOWN_ALIAS = "unknown-alias"
    UNHANDLED_EVENT = "unhandled-event"
    OUT_OF_SCOPE = "out-of-scope"
