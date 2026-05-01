"""Deterministic (non-LLM) lint checks for the knowledge base."""

from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from scripts.core.redact import redact as _redact_text
from scripts.core.render import Schema, load_schemas
from scripts.core.utils import (
    count_inbound_links,
    extract_wikilinks,
    file_hash,
    get_article_word_count,
    get_frontmatter_list,
    get_frontmatter_scalar,
    list_raw_files,
    list_wiki_articles,
    load_state,
    wiki_article_exists,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from scripts.commands.lint.report import LintIssue
    from scripts.core.config import Config

__all__ = [
    "_registry",
    "check_article_in_index",
    "check_broken_links",
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
    "get_required_sections",
    "run_all",
]


@cache
def _registry(config: Config) -> dict[str, Schema]:
    try:
        return load_schemas(config.wiki)
    except RuntimeError:
        return {}


def get_required_sections(config: Config, type_: str) -> tuple[str, ...]:
    """Required section titles for an article type, or () for unknown type."""
    schema = _registry(config).get(type_)
    return schema.required_sections if schema else ()


_get_frontmatter_field = get_frontmatter_scalar  # backward-compat alias


def check_broken_links(config: Config) -> list[LintIssue]:
    """Check for [[wikilinks]] that point to non-existent articles."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(wiki)
        for link in extract_wikilinks(content):
            if link.startswith(("daily/", "sources/")):
                continue  # external refs (daily/, sources/) live outside the wiki dir
            if not wiki_article_exists(config, link):
                issues.append(
                    {
                        "severity": "error",
                        "check": "broken_link",
                        "file": str(rel),
                        "detail": f"Broken link: [[{link}]] - target does not exist",
                    }
                )
    return issues


def check_orphan_pages(config: Config) -> list[LintIssue]:
    """Check for articles with zero inbound links."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        rel = article.relative_to(wiki)
        # Wikilinks use `.md` without quotes here as part of the wikilink <-> slug
        # conversion (not a filesystem filename literal); leave as-is on this and
        # the other similar sites in this file.
        link_target = str(rel).replace(".md", "").replace("\\", "/")
        inbound = count_inbound_links(config, link_target)
        if inbound == 0:
            issues.append(
                {
                    "severity": "warning",
                    "check": "orphan_page",
                    "file": str(rel),
                    "detail": f"Orphan page: no other articles link to [[{link_target}]]",
                }
            )
    return issues


def check_orphan_sources(config: Config) -> list[LintIssue]:
    """Check for daily logs that haven't been compiled yet."""
    state = load_state(config)
    ingested = state.get("ingested", {})
    return [
        {
            "severity": "warning",
            "check": "orphan_source",
            "file": f"daily/{log_path.name}",
            "detail": f"Uncompiled daily log: {log_path.name} has not been ingested",
        }
        for log_path in list_raw_files(config)
        if log_path.name not in ingested
    ]


def check_stale_articles(config: Config) -> list[LintIssue]:
    """Check if source daily logs have changed since compilation."""
    state = load_state(config)
    ingested = state.get("ingested", {})
    issues: list[LintIssue] = []
    for log_path in list_raw_files(config):
        rel = log_path.name
        if rel in ingested:
            stored_hash = ingested[rel].get("hash", "")
            current_hash = file_hash(log_path)
            if stored_hash != current_hash:
                issues.append(
                    {
                        "severity": "warning",
                        "check": "stale_article",
                        "file": f"daily/{rel}",
                        "detail": f"Stale: {rel} has changed since last compilation",
                    }
                )
    return issues


def check_missing_backlinks(config: Config) -> list[LintIssue]:
    """Check for asymmetric links: A links to B but B doesn't link to A."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        content = article.read_text(encoding="utf-8")
        rel = article.relative_to(wiki)
        source_link = str(rel).replace(".md", "").replace("\\", "/")

        for link in extract_wikilinks(content):
            if link.startswith(("daily/", "sources/")):
                continue
            target_path = wiki / f"{link}.md"
            if target_path.exists():
                target_content = target_path.read_text(encoding="utf-8")
                if f"[[{source_link}]]" not in target_content:
                    issues.append(
                        {
                            "severity": "suggestion",
                            "check": "missing_backlink",
                            "file": str(rel),
                            "detail": f"[[{source_link}]] links to [[{link}]] but not vice versa",
                            "auto_fixable": True,
                        }
                    )
    return issues


def check_sparse_articles(config: Config) -> list[LintIssue]:
    """Check for articles with fewer than 200 words."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        word_count = get_article_word_count(article)
        if word_count < 200:
            rel = article.relative_to(wiki)
            issues.append(
                {
                    "severity": "suggestion",
                    "check": "sparse_article",
                    "file": str(rel),
                    "detail": f"Sparse article: {word_count} words (minimum recommended: 200)",
                }
            )
    return issues


def check_missing_sections(config: Config) -> list[LintIssue]:
    """Check that each typed article contains all required sections for its type."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        content = article.read_text(encoding="utf-8")
        article_type = _get_frontmatter_field(content, "type")
        required = get_required_sections(config, article_type) if article_type else ()
        if not required:
            continue
        rel = article.relative_to(wiki)
        missing = [section for section in required if f"## {section}" not in content]
        if missing:
            issues.append(
                {
                    "severity": "warning",
                    "check": "missing_sections",
                    "file": str(rel),
                    "detail": f"Type '{article_type}' missing required sections: {', '.join(missing)}",
                }
            )
    return issues


def check_low_confidence(config: Config) -> list[LintIssue]:
    """Flag articles with confidence: low that have no explanatory note in the body."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        content = article.read_text(encoding="utf-8")
        if _get_frontmatter_field(content, "confidence") != "low":
            continue
        rel = article.relative_to(wiki)
        # Strip frontmatter to check body only
        body_start = content.find("---", 3)
        body = content[body_start + 3 :] if body_start != -1 else content
        if "low confidence" not in body.lower():
            issues.append(
                {
                    "severity": "warning",
                    "check": "low_confidence",
                    "file": str(rel),
                    "detail": (
                        "confidence: low but no explanation in body. "
                        "Add a note: '> **Low confidence:** reason'"
                    ),
                }
            )
    return issues


def check_article_in_index(config: Config) -> list[LintIssue]:
    """Check that every wiki article appears in wiki/index.md."""
    if not config.index_file.exists():
        return []
    index_content = config.index_file.read_text(encoding="utf-8")
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        rel = article.relative_to(config.wiki)
        link = str(rel).replace(".md", "").replace("\\", "/")
        if f"[[{link}]]" not in index_content:
            issues.append(
                {
                    "severity": "warning",
                    "check": "article_not_in_index",
                    "file": str(rel),
                    "detail": f"[[{link}]] not found in wiki/index.md",
                }
            )
    return issues


def check_orphaned_articles(config: Config) -> list[LintIssue]:
    """Flag articles whose every `sources:` entry is missing from disk.

    Policy: orphaned only when ALL sources are gone. At least one surviving
    source keeps the article grounded (partial-loss articles are fine).
    """
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        try:
            content = article.read_text(encoding="utf-8")
        except OSError:
            continue
        sources = get_frontmatter_list(content, "sources")
        if not sources:
            continue
        missing = [s for s in sources if not (config.root / s).exists()]
        if len(missing) == len(sources):
            rel = article.relative_to(config.wiki)
            issues.append(
                {
                    "severity": "warning",
                    "check": "orphaned_article",
                    "file": str(rel),
                    "detail": f"All sources missing on disk: {', '.join(missing)}",
                    "auto_fixable": True,
                }
            )
    return issues


def check_truncated_articles(config: Config) -> list[LintIssue]:
    """Flag articles with truncated: true in frontmatter.

    Suggests a recompile once the contributing daily log's full text is
    available. Compile-agent clears the flag when no contributing section
    carries the truncation marker.
    """
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        try:
            content = article.read_text(encoding="utf-8")
        except OSError:
            continue
        if get_frontmatter_scalar(content, "truncated").lower() != "true":
            continue
        rel = article.relative_to(wiki)
        issues.append(
            {
                "severity": "suggestion",
                "check": "truncated_article",
                "file": str(rel),
                "detail": (
                    "truncated: true — recompile when the contributing "
                    "daily log's full text is available"
                ),
            }
        )
    return issues


def check_secrets(config: Config) -> list[LintIssue]:
    """Check all wiki articles for unredacted secrets (API keys, tokens, etc.)."""
    wiki = config.wiki
    issues: list[LintIssue] = []
    for article in list_wiki_articles(config):
        rel = article.relative_to(wiki)
        content = article.read_text(encoding="utf-8")
        _, notices = _redact_text(content)
        issues.extend(
            {
                "severity": "error",
                "check": "secret_detected",
                "file": str(rel),
                "detail": notice,
                "auto_fixable": True,
            }
            for notice in notices
        )
    return issues


# Ordered list of (display_name, check_fn) for the main loop.
STRUCTURAL_CHECKS: list[tuple[str, Callable[[Config], list[LintIssue]]]] = [
    ("Broken links", check_broken_links),
    ("Orphan pages", check_orphan_pages),
    ("Orphan sources", check_orphan_sources),
    ("Stale articles", check_stale_articles),
    ("Missing backlinks", check_missing_backlinks),
    ("Sparse articles", check_sparse_articles),
    ("Missing sections", check_missing_sections),  # V2
    ("Low confidence", check_low_confidence),  # V2
    ("Article in index", check_article_in_index),  # V2
    ("Orphaned articles", check_orphaned_articles),
    ("Truncated articles", check_truncated_articles),
    ("Secrets", check_secrets),
]


def run_all(config: Config) -> list[LintIssue]:
    """Run all structural checks and return the combined issue list."""
    issues: list[LintIssue] = []
    for _name, check_fn in STRUCTURAL_CHECKS:
        issues.extend(check_fn(config))
    return issues
