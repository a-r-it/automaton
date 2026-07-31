"""Veto EnterPlanMode in architect sessions with an architect-correct teach
message. The architect authors OpenSpec artifacts in normal mode and ends
at the approved design; plan mode restricts Write/Edit and has no clean
exit."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from hook_common import NO_TASK, Context  # noqa: E402
from plugin_contract import EnvVar, RuleName, TraceEvent  # noqa: E402

NAME = RuleName.PLANMODE_BAN

_MESSAGE = f"""PLAN MODE IS DISABLED FOR THE ARCHITECT

You are the architect -- an OpenSpec design flow that authors the change's
artifacts (proposal, delta specs, design) in normal mode and ends at the
approved design. Plan mode restricts Write/Edit and has no clean exit; the
architect never needs it.

Continue in normal mode instead:
  - keep following the current artifact's authoring graph,
  - lay the graph's stages out as tasks and work them there,
  - the flow ends at the approved design -- no plan files, no handoff.

(Override for humans: {EnvVar.WARDEN}=0.)"""


def check(ctx: Context) -> str | None:
    ctx.trace(NO_TASK, TraceEvent.BLOCK, "enterplanmode")
    return _MESSAGE
