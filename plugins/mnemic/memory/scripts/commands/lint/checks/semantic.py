"""LLM-based lint checks for the knowledge base."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.core.agent import ANALYSIS_OPTIONS, run_agent
from scripts.core.utils import read_all_wiki_content
from scripts.prompts import build_lint_semantic

if TYPE_CHECKING:
    from scripts.commands.lint.report import LintIssue
    from scripts.core.config import Config

__all__ = [
    "check_contradictions",
]


async def check_contradictions(config: Config) -> list[LintIssue]:
    """Use LLM to detect contradictions across articles."""
    wiki_content = read_all_wiki_content(config)

    prompt = build_lint_semantic(wiki_content=wiki_content)

    response = ""
    try:
        result = await run_agent(prompt, cwd=config.root, options=ANALYSIS_OPTIONS)
        response = result.text
    except Exception as exc:  # noqa: BLE001  # any agent failure → structured lint issue
        return [
            {
                "severity": "error",
                "check": "contradiction",
                "file": "(system)",
                "detail": f"LLM check failed: {exc}",
            }
        ]

    issues: list[LintIssue] = []
    if "NO_ISSUES" not in response:
        for issue_line in response.strip().split("\n"):
            line = issue_line.strip()
            if line.startswith(("CONTRADICTION:", "INCONSISTENCY:")):
                issues.append(
                    {
                        "severity": "warning",
                        "check": "contradiction",
                        "file": "(cross-article)",
                        "detail": line,
                    }
                )

    return issues
