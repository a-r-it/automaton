"""Single facade over claude_agent_sdk — one run loop, named presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "ANALYSIS_OPTIONS",
    "COMMIT_OPTIONS",
    "COMPILE_OPTIONS",
    "QUERY_FILEBACK_OPTIONS",
    "QUERY_OPTIONS",
    "AgentOptions",
    "AgentResult",
    "run_agent",
]

_SONNET = "claude-sonnet-4-6"
_HAIKU = "claude-haiku-4-5"

type _Effort = Literal["low", "medium", "high", "max"]
type _PermissionMode = Literal[
    "default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"
]


@dataclass(frozen=True, slots=True)
class AgentOptions:
    """Call profile for a single run_agent() invocation."""

    tools: tuple[str, ...] = ()
    max_turns: int = 15
    system_prompt: dict[str, str] | None = None
    permission_mode: _PermissionMode | None = None
    effort: _Effort | None = "medium"
    model: str = _SONNET
    setting_sources: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Aggregated output of one run_agent() call."""

    text: str
    cost_usd: float


COMPILE_OPTIONS = AgentOptions(
    tools=("Read", "Write", "Edit", "Glob", "Grep"),
    max_turns=30,
    system_prompt={"type": "preset", "preset": "claude_code"},
    permission_mode="acceptEdits",
    effort="medium",
    setting_sources=("",),
)

QUERY_OPTIONS = AgentOptions(
    tools=("Read", "Grep", "Glob"),
    max_turns=15,
    system_prompt={"type": "preset", "preset": "claude_code"},
    permission_mode="acceptEdits",
    effort="medium",
    setting_sources=("",),
)

QUERY_FILEBACK_OPTIONS = AgentOptions(
    tools=("Read", "Grep", "Glob", "Write", "Edit"),
    max_turns=15,
    system_prompt={"type": "preset", "preset": "claude_code"},
    permission_mode="acceptEdits",
    effort="medium",
    setting_sources=("",),
)

ANALYSIS_OPTIONS = AgentOptions(
    tools=(),
    max_turns=2,
    effort="medium",  # explicitly match original flush/semantic behavior
    permission_mode=None,  # not forwarded — matches original
    setting_sources=("",),
)

COMMIT_OPTIONS = AgentOptions(
    tools=(),
    max_turns=1,
    model=_HAIKU,
    effort=None,  # not forwarded — matches original commit.py
    permission_mode=None,  # not forwarded — matches original commit.py
    setting_sources=("",),
)


async def run_agent(
    prompt: str,
    cwd: Path,
    options: AgentOptions,
) -> AgentResult:
    """Run a claude_agent_sdk query and return aggregated text + cost."""
    from claude_agent_sdk import (  # lazy — not imported until first call
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    sdk_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "allowed_tools": list(options.tools),
        "max_turns": options.max_turns,
        "model": options.model,
    }
    if options.effort is not None:
        sdk_kwargs["effort"] = options.effort
    if options.permission_mode is not None:
        sdk_kwargs["permission_mode"] = options.permission_mode
    if options.system_prompt is not None:
        sdk_kwargs["system_prompt"] = options.system_prompt
    if options.setting_sources is not None:
        sdk_kwargs["setting_sources"] = list(options.setting_sources)

    text = ""
    cost_usd = 0.0
    async for message in query(prompt=prompt, options=ClaudeAgentOptions(**sdk_kwargs)):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text += block.text
        elif isinstance(message, ResultMessage):
            cost_usd = message.total_cost_usd or 0.0
    return AgentResult(text=text, cost_usd=cost_usd)
