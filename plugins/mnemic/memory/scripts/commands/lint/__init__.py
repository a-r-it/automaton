"""
Lint the knowledge base for structural and semantic health.

Runs structural and LLM-based checks. See `main()` for the registered list.

Usage:
    uv run python lint.py                    # all checks
    uv run python lint.py --structural       # skip LLM checks (faster, cheaper)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from scripts.commands.lint.checks.semantic import check_contradictions
from scripts.commands.lint.checks.structural import (
    STRUCTURAL_CHECKS,
    _registry,
    check_article_in_index,
    check_broken_links,
    check_low_confidence,
    check_missing_backlinks,
    check_missing_sections,
    check_orphan_pages,
    check_orphan_sources,
    check_orphaned_articles,
    check_secrets,
    check_sparse_articles,
    check_stale_articles,
    check_truncated_articles,
    get_required_sections,
)
from scripts.commands.lint.report import LintIssue, generate_report
from scripts.core.cli import CliContextP, cli_main
from scripts.core.config import now_iso, today_iso
from scripts.core.constants import LINT_REPORT_FMT
from scripts.core.errors import EnvError
from scripts.core.exit_codes import ExitCode
from scripts.core.utils import load_state, save_state

__all__ = [
    "LintIssue",
    "_registry",
    "build_parser",
    "check_article_in_index",
    "check_broken_links",
    "check_contradictions",
    "check_low_confidence",
    "check_missing_backlinks",
    "check_missing_sections",
    "check_orphan_pages",
    "check_orphan_sources",
    "check_orphaned_articles",
    "check_secrets",
    "check_sparse_articles",
    "check_stale_articles",
    "check_truncated_articles",
    "generate_report",
    "get_required_sections",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint the knowledge base")
    parser.add_argument(
        "--structural",
        action="store_true",
        help="Skip LLM-based checks (contradictions) - faster and free",
    )
    return parser


@cli_main(name="lint", parser_factory=build_parser)
def main(ctx: CliContextP) -> ExitCode:
    args = ctx.args

    print("Running knowledge base lint checks...")
    all_issues: list[LintIssue] = []

    # Structural checks (free, instant)
    for name, check_fn in STRUCTURAL_CHECKS:
        print(f"  Checking: {name}...")
        issues = check_fn(ctx.config)
        all_issues.extend(issues)
        print(f"    Found {len(issues)} issue(s)")

    # LLM check (costs money)
    if not args.structural:
        print("  Checking: Contradictions (LLM)...")
        issues = asyncio.run(check_contradictions(ctx.config))
        all_issues.extend(issues)
        print(f"    Found {len(issues)} issue(s)")
    else:
        print("  Skipping: Contradictions (--structural)")

    # Generate and save report
    report = generate_report(all_issues)
    try:
        reports = ctx.config.reports
        reports.mkdir(parents=True, exist_ok=True)
        report_path = reports / LINT_REPORT_FMT.format(date=today_iso())
        report_path.write_text(report, encoding="utf-8")
    except OSError as exc:
        raise EnvError(
            exit_code=ExitCode.FILE_WRITE,
            action="write-lint-report",
            underlying=str(exc),
            hint="check filesystem permissions for the lint reports directory",
        ) from exc
    print(f"\nReport saved to: {report_path}")

    # Update state
    state = load_state(ctx.config)
    state["last_lint"] = now_iso()
    save_state(ctx.config, state)

    # Summary
    errors = sum(1 for i in all_issues if i["severity"] == "error")
    warnings = sum(1 for i in all_issues if i["severity"] == "warning")
    suggestions = sum(1 for i in all_issues if i["severity"] == "suggestion")
    print(f"\nResults: {errors} errors, {warnings} warnings, {suggestions} suggestions")

    if errors > 0:
        print("\nErrors found - knowledge base needs attention!")
        return ExitCode.LINT_ERRORS_FOUND
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
