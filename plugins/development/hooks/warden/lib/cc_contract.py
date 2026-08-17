"""Claude Code's own vocabulary consumed by warden: hook events, tool names,
hook-payload fields. Nothing plugin-invented lives here (that is
plugin_contract.py)."""
from __future__ import annotations

from enum import StrEnum


class HookEvent(StrEnum):
    PRE_TOOL_USE = "PreToolUse"


class Tool(StrEnum):
    ENTER_PLAN_MODE = "EnterPlanMode"


class Field(StrEnum):
    # hook payload envelope
    HOOK_EVENT_NAME = "hook_event_name"
    TOOL_NAME = "tool_name"
    AGENT_TYPE = "agent_type"
    SESSION_ID = "session_id"
    TRANSCRIPT_PATH = "transcript_path"
    CWD = "cwd"
    TOOL_INPUT = "tool_input"
