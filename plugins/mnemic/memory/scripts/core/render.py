"""Schema registry loader and compile-prompt renderer.

Replaces the previously-monolithic LIBRARIAN.md. Schemas live in the
user's wiki at <WIKI>/*/_schema.md. This module parses them into a
registry and renders the compile prompt by injecting dynamic tables
and article formats into `memory/librarian/static.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

from scripts.core.constants import SCHEMA_GLOB

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class Schema:
    """Parsed schema for one article type."""

    type: str
    routing_signal: str
    required_sections: tuple[str, ...]
    tiebreaker: str | None
    description: str
    article_template: str


def load_schemas(wiki_dir: Path) -> dict[str, Schema]:
    """Load all `_schema.md` files under `wiki_dir/*/_schema.md`.

    Args:
        wiki_dir: Path to the user's wiki root.

    Returns:
        Mapping of `type:` → `Schema`, one entry per found schema.

    Raises:
        RuntimeError: on duplicate type, missing mandatory frontmatter
            field, missing `## Article template` section, or an empty
            registry.
    """
    registry: dict[str, Schema] = {}
    for path in sorted(wiki_dir.glob(SCHEMA_GLOB)):
        schema = _parse_schema(path)
        if schema.type in registry:
            raise RuntimeError(
                f"duplicate schema type '{schema.type}' in {path} (already declared elsewhere)"
            )
        registry[schema.type] = schema
    if not registry:
        raise RuntimeError(f"no schemas found in {wiki_dir}; run mnemic:wiki setup")
    return registry


def _parse_schema(path: Path) -> Schema:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise RuntimeError(f"{path}: missing YAML frontmatter opening '---'")
    closing = raw.find("\n---\n", 4)
    if closing == -1:
        raise RuntimeError(f"{path}: missing YAML frontmatter closing '---'")
    frontmatter_raw = raw[4:closing]
    body = raw[closing + 5 :]

    meta = yaml.safe_load(frontmatter_raw) or {}
    for field in ("type", "routing_signal", "required_sections"):
        if field not in meta:
            raise RuntimeError(f"{path}: missing required frontmatter field '{field}'")

    description, article_template = _split_body(body, path)

    return Schema(
        type=str(meta["type"]),
        routing_signal=str(meta["routing_signal"]),
        required_sections=tuple(str(s) for s in meta["required_sections"]),
        tiebreaker=str(meta["tiebreaker"]) if "tiebreaker" in meta else None,
        description=description.strip(),
        article_template=article_template,
    )


def _split_body(body: str, path: Path) -> tuple[str, str]:
    marker = "## Article template"
    idx = body.find(marker)
    if idx == -1:
        raise RuntimeError(f"{path}: missing mandatory section '## Article template'")
    description = body[:idx]
    tail = body[idx + len(marker) :].lstrip("\n")
    fence_start = tail.find("```")
    if fence_start == -1:
        raise RuntimeError(f"{path}: '## Article template' has no fenced code block")
    after_fence = tail[fence_start:]
    # skip opening fence line (may include language hint)
    newline = after_fence.find("\n")
    rest = after_fence[newline + 1 :]
    fence_end = rest.find("```")
    if fence_end == -1:
        raise RuntimeError(f"{path}: '## Article template' fenced block is unterminated")
    template = rest[:fence_end]
    return description, template


def render_prompt(
    registry: dict[str, Schema],
    static_md: str,
    *,
    wiki: str,
    daily: str,
    sources: str,
) -> str:
    """Render the compile prompt by injecting registry-derived blocks.

    Substitutes:
      - ``{{ROUTING_TABLE}}`` / ``{{REQUIRED_SECTIONS_TABLE}}`` /
        ``{{ARTICLE_FORMATS}}`` / ``{{TIEBREAKERS}}`` from the registry
      - ``{{WIKI}}`` / ``{{DAILY}}`` / ``{{SOURCES}}`` from arguments

    Fails fast on any unresolved ``{{…}}`` token remaining in the output.

    Args:
        registry: Schema registry produced by ``load_schemas``.
        static_md: Content of ``memory/librarian/static.md``.
        wiki: Resolved wiki directory name (e.g. ``"wiki"``).
        daily: Resolved daily directory name (e.g. ``"daily"``).
        sources: Resolved sources directory name (e.g. ``"sources"``).

    Returns:
        Fully rendered compile prompt as a string.

    Raises:
        RuntimeError: If any ``{{…}}`` placeholder remains unresolved.
    """
    out = static_md
    out = out.replace("{{ROUTING_TABLE}}", _render_routing_table(registry))
    out = out.replace("{{REQUIRED_SECTIONS_TABLE}}", _render_required_sections_table(registry))
    out = out.replace("{{ARTICLE_FORMATS}}", _render_article_formats(registry))
    out = out.replace("{{TIEBREAKERS}}", _render_tiebreakers(registry))
    out = out.replace("{{WIKI}}", wiki)
    out = out.replace("{{DAILY}}", daily)
    out = out.replace("{{SOURCES}}", sources)

    if "{{" in out:
        leftover = out[out.index("{{") : out.index("{{") + 40]
        raise RuntimeError(f"unresolved placeholder in rendered prompt: {leftover!r}")
    return out


def _render_routing_table(registry: dict[str, Schema]) -> str:
    rows = [
        "| Content signal | → type |",
        "|----------------|--------|",
    ]
    rows.extend(f"| {schema.routing_signal} | `{schema.type}` |" for schema in registry.values())
    return "\n".join(rows)


def _render_required_sections_table(registry: dict[str, Schema]) -> str:
    rows = [
        "| Type | Required Sections |",
        "|------|-------------------|",
    ]
    rows.extend(
        f"| `{schema.type}` | {', '.join(schema.required_sections)} |"
        for schema in registry.values()
    )
    return "\n".join(rows)


def _render_article_formats(registry: dict[str, Schema]) -> str:
    blocks = [
        f"### `{schema.type}` articles\n\n"
        f"{schema.description}\n\n"
        f"```markdown\n{schema.article_template}```\n"
        for schema in registry.values()
    ]
    return "\n".join(blocks)


def _render_tiebreakers(registry: dict[str, Schema]) -> str:
    lines = [
        f"**Tiebreaker:** {schema.tiebreaker}" for schema in registry.values() if schema.tiebreaker
    ]
    return "\n\n".join(lines)
