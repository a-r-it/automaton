"""Result types and report generation for lint."""

from __future__ import annotations

from typing import Any

from scripts.core.config import today_iso

__all__ = [
    "LintIssue",
    "generate_report",
]

# A single lint issue: dict with "severity", "check", "file", "detail",
# and optional "auto_fixable".
LintIssue = dict[str, Any]


def generate_report(all_issues: list[LintIssue]) -> str:
    """Generate a markdown lint report."""
    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]
    suggestions = [i for i in all_issues if i["severity"] == "suggestion"]

    lines = [
        f"# Lint Report - {today_iso()}",
        "",
        f"**Total issues:** {len(all_issues)}",
        f"- Errors: {len(errors)}",
        f"- Warnings: {len(warnings)}",
        f"- Suggestions: {len(suggestions)}",
        "",
    ]

    for severity, issues, marker in [
        ("Errors", errors, "x"),
        ("Warnings", warnings, "!"),
        ("Suggestions", suggestions, "?"),
    ]:
        if issues:
            lines.append(f"## {severity}")
            lines.append("")
            for issue in issues:
                fixable = " (auto-fixable)" if issue.get("auto_fixable") else ""
                lines.append(
                    f"- **[{marker}]** [{issue['check']}] `{issue['file']}` - {issue['detail']}{fixable}"
                )
            lines.append("")

    if not all_issues:
        lines.append("All checks passed. Knowledge base is healthy.")
        lines.append("")

    return "\n".join(lines)
