"""Typed shapes for every payload warden consumes. Pure stdlib dataclasses:
no I/O, no policy. Parse posture: every from_dict is lenient and never
raises -- wrong-typed/missing values collapse to empty defaults. HookPayload
is the one shape that records envelope `problems`."""
from __future__ import annotations

import dataclasses
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cc_contract import Field  # noqa: E402


def _str(raw: dict[str, Any], key: str, default: str = "") -> str:
    val = raw.get(key, default)
    return val if isinstance(val, str) else default


@dataclasses.dataclass
class AgentInput:
    """The Agent tool_input fields model_routing reads."""

    model: str = ""
    subagent_type: str = ""

    @staticmethod
    def from_dict(raw: Any) -> AgentInput:
        if not isinstance(raw, dict):
            raw = {}
        return AgentInput(
            model=_str(raw, Field.MODEL),
            subagent_type=_str(raw, Field.SUBAGENT_TYPE),
        )


@dataclasses.dataclass
class HookPayload:
    hook_event_name: str = ""
    tool_name: str = ""
    agent_type: str = ""
    session_id: str = ""
    transcript_path: str = ""
    cwd: str = ""  # documented hook stdin field; "" => routing falls back to os.getcwd()
    tool_input: dict[str, Any] = dataclasses.field(default_factory=dict)
    problems: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> HookPayload:
        if not isinstance(raw, dict):
            raw = {}
        problems: list[str] = []
        tool_input = raw.get(Field.TOOL_INPUT)
        if tool_input is None:
            tool_input = {}
        elif not isinstance(tool_input, dict):
            problems.append("tool_input: not a dict -> {}")
            tool_input = {}
        return HookPayload(
            hook_event_name=_str(raw, Field.HOOK_EVENT_NAME),
            tool_name=_str(raw, Field.TOOL_NAME),
            agent_type=_str(raw, Field.AGENT_TYPE),
            session_id=_str(raw, Field.SESSION_ID),
            transcript_path=_str(raw, Field.TRANSCRIPT_PATH),
            cwd=_str(raw, Field.CWD),
            tool_input=tool_input,
            problems=problems,
        )

    def agent_input(self) -> AgentInput:
        return AgentInput.from_dict(self.tool_input)
