"""Shared utilities for the wiki knowledge base."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from scripts.core.config import Config, now_iso
from scripts.core.constants import INTERNAL_ARTICLE_FILES, MARKDOWN_GLOB, SCHEMA_GLOB, SourceType

if TYPE_CHECKING:
    from pathlib import Path


def _article_dirs(config: Config) -> list[Path]:
    """All directories that contain article files (detected by _schema.md presence)."""
    return sorted(path.parent for path in config.wiki.glob(SCHEMA_GLOB))


# ── State management ──────────────────────────────────────────────────


def load_state(config: Config) -> dict[str, Any]:
    """Load persistent state from state.json."""
    state_file = config.state_file
    if state_file.exists():
        data: dict[str, Any] = json.loads(state_file.read_text(encoding="utf-8"))
        return data
    return {"ingested": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}


def save_state(config: Config, state: dict[str, Any]) -> None:
    """Save state to state.json."""
    config.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def update_state(
    config: Config,
    path: Path,
    hash_val: str,
    source_type: SourceType = "daily",
) -> None:
    """Mark a compiled file in state.json.

    source_type: 'daily' stores under state['ingested'][filename]
                 'source' stores under state['sources'][filename]
    """
    state = load_state(config)
    entry = {"hash": hash_val, "compiled_at": now_iso()}
    if source_type == "source":
        state.setdefault("sources", {})[path.name] = entry
    else:
        state.setdefault("ingested", {})[path.name] = entry
    save_state(config, state)


# ── File hashing ──────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    """SHA-256 hash of a file (first 16 hex chars)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# Backward-compat alias — compile.py imports file_hash
file_hash = sha256_file


# ── Frontmatter parsing ───────────────────────────────────────────────


def _split_frontmatter(content: str) -> tuple[str, str] | None:
    """Return (frontmatter_body, rest) if content has YAML frontmatter, else None.

    frontmatter_body excludes the leading/trailing ``---`` fences.
    rest starts right after the closing ``---`` and its trailing newline.
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    fm_start = 4 if len(content) > 3 and content[3] == "\n" else 3
    fm_body = content[fm_start:end]
    after = end + len("\n---")
    if after < len(content) and content[after] == "\n":
        after += 1
    return fm_body, content[after:]


def get_frontmatter_scalar(content: str, field: str) -> str:
    """Extract a single scalar field value from YAML frontmatter.

    Empty string if the field is absent, the content has no frontmatter,
    or the frontmatter is unclosed.
    """
    split = _split_frontmatter(content)
    if split is None:
        return ""
    fm, _ = split
    for line in fm.splitlines():
        if line.startswith(f"{field}:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def get_frontmatter_list(content: str, field: str) -> list[str]:
    """Extract a block-style YAML list field from frontmatter.

    Only block style is supported:

        sources:
          - "daily/2026-04-01.md"
          - "sources/foo.md"

    Inline lists (``field: [a, b]``), scalar values, missing fields, and
    malformed bodies return ``[]``. No exceptions raised.
    """
    split = _split_frontmatter(content)
    if split is None:
        return []
    fm, _ = split
    items: list[str] = []
    in_field = False
    for line in fm.splitlines():
        stripped = line.strip()
        if not in_field:
            if line.startswith(f"{field}:"):
                rest = line.split(":", 1)[1].strip()
                if rest:
                    # inline list or scalar — not a block list
                    return []
                in_field = True
            continue
        # in_field: accept indented "- value" lines; stop on unindented non-empty
        if stripped == "":
            continue
        if not line.startswith((" ", "\t")):
            break
        if stripped.startswith("- "):
            items.append(stripped[2:].strip().strip('"').strip("'"))
    return items


# ── Slug / naming ─────────────────────────────────────────────────────


def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ── Wikilink helpers ──────────────────────────────────────────────────


_CODE_SPAN_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def extract_wikilinks(content: str) -> list[str]:
    """Extract unique [[wikilinks]] from markdown content, preserving order.

    Strips fenced code blocks and inline code spans first so prose mentions
    of Obsidian syntax (e.g. ``\\`[[wikilinks]]\\```) are not treated as links.
    """
    stripped = _CODE_SPAN_RE.sub("", content)
    return list(dict.fromkeys(re.findall(r"\[\[([^\]]+)\]\]", stripped)))


def wiki_article_exists(config: Config, link: str) -> bool:
    """Check if a wikilinked article exists on disk."""
    # Wikilinks use `.md` here as part of the wikilink <-> filename-stem
    # conversion (part of the wikilink grammar, not a filesystem filename
    # literal) — leave the `.md` literal on this line and the similar one
    # below.
    path = config.wiki / f"{link}.md"
    return path.exists()


# ── Wiki content helpers ──────────────────────────────────────────────


def read_wiki_index(config: Config) -> str:
    """Read the knowledge base index file."""
    index_file = config.index_file
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "# Knowledge Base Index\n\n| Article | Summary | Compiled From | Updated |\n|---------|---------|---------------|---------|"


def read_all_wiki_content(config: Config) -> str:
    """Read index + all wiki articles into a single string for context."""
    parts = [f"## INDEX\n\n{read_wiki_index(config)}"]

    for subdir in _article_dirs(config):
        if not subdir.exists():
            continue
        for md_file in sorted(subdir.glob(MARKDOWN_GLOB)):
            rel = md_file.relative_to(config.wiki)
            content = md_file.read_text(encoding="utf-8")
            parts.append(f"## {rel}\n\n{content}")

    return "\n\n---\n\n".join(parts)


def list_wiki_articles(config: Config) -> list[Path]:
    """List all wiki article files."""
    articles: list[Path] = []
    for subdir in _article_dirs(config):
        if subdir.exists():
            articles.extend(
                p
                for p in sorted(subdir.glob(MARKDOWN_GLOB))
                if p.name not in INTERNAL_ARTICLE_FILES
            )
    return articles


def list_raw_files(config: Config) -> list[Path]:
    """List all daily log files."""
    if not config.daily.exists():
        return []
    return sorted(config.daily.glob(MARKDOWN_GLOB))


def list_daily_files(config: Config, *, changed_only: bool = True) -> list[dict[str, Path | str]]:
    """List daily log files with their hashes.

    With changed_only=True, skips files whose hash matches state.json.
    Returns list of dicts: {path: Path, hash: str}
    """
    if not config.daily.exists():
        return []
    state = load_state(config)
    ingested = state.get("ingested", {})
    result: list[dict[str, Path | str]] = []
    for path in sorted(config.daily.glob(MARKDOWN_GLOB)):
        h = sha256_file(path)
        if changed_only and ingested.get(path.name, {}).get("hash") == h:
            continue
        result.append({"path": path, "hash": h})
    return result


def list_source_files(config: Config, *, new_only: bool = True) -> list[dict[str, Path | str]]:
    """List source files with their hashes.

    With new_only=True, skips files already tracked in state.json under 'sources'.
    Returns list of dicts: {path: Path, hash: str}
    """
    if not config.sources.exists():
        return []
    state = load_state(config)
    compiled = state.get("sources", {})
    result: list[dict[str, Path | str]] = []
    for path in sorted(config.sources.glob(MARKDOWN_GLOB)):
        h = sha256_file(path)
        if new_only and path.name in compiled:
            continue
        result.append({"path": path, "hash": h})
    return result


# ── Index helpers ─────────────────────────────────────────────────────


def count_inbound_links(
    config: Config,
    target: str,
    exclude_file: Path | None = None,
) -> int:
    """Count how many wiki articles link to a given target."""
    count = 0
    for article in list_wiki_articles(config):
        if article == exclude_file:
            continue
        content = article.read_text(encoding="utf-8")
        if f"[[{target}]]" in content:
            count += 1
    return count


def get_article_word_count(path: Path) -> int:
    """Count words in an article, excluding YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    # Strip frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3 :]
    return len(content.split())


def build_index_entry(rel_path: str, summary: str, sources: str, updated: str) -> str:
    """Build a single index table row."""
    link = rel_path.replace(".md", "")
    return f"| [[{link}]] | {summary} | {sources} | {updated} |"
