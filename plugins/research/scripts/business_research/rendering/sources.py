"""Source merging and the sources appendix (V2 spec §8 item 8)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from business_research import json_io
from business_research.rendering.localization import (
    LABELS,
    Labels,
    _lang,
    _wrap_section,
    esc,
    safe_url,
)

if TYPE_CHECKING:
    from business_research.rendering.report import Run


@dataclass(frozen=True)
class SourceMention:
    """One agent's or verifier's own reference to a source, folded into a
    `MergedSource` by canonical URL (spec §7 dedup rule, §8 item 8).
    `reachability` is populated only for `origin == "panel"` mentions (drawn
    from that agent's own verification document); it stays `None` for
    verifier mentions, which carry no reachability concept of their own."""

    origin: str  # "panel" | "verifier"
    agent: str
    local_id: str
    detail: str  # the source's "usage" text
    reachability: str | None


@dataclass(frozen=True)
class MergedSource:
    """One deduplicated entry in the sources appendix (spec §8 item 8):
    every raw source sharing `canonical_url` folds into one of these.
    `title`/`publisher` come from the first mention encountered in
    `merged_sources`' roster-then-registry walk (spec: "first by roster
    order wins" — every raw variant still lives in the embedded provenance
    block, so nothing is lost). `mentions` preserves every contributing
    origin's own local id, usage/status text, and reachability for display.
    `anchor_id` is this entry's `id="src-..."` target — see
    `_source_anchor_id`."""

    canonical_url: str
    title: str
    publisher: str
    mentions: tuple[SourceMention, ...]
    anchor_id: str


class _SourceGroup(TypedDict):
    """`merged_sources`' own in-progress bookkeeping for one canonical-URL
    group, before it's frozen into a `MergedSource` — not a wire document
    shape, so it lives here rather than in `models.py`."""

    title: str
    publisher: str
    mentions: list[SourceMention]


# `_numeric_suffix`/`_sorted_by_numeric_id` are plan-mandated for Task 13
# (rendering/sections.py) but `merged_sources` below already depends on them
# and sources.py is the lowest module in the DAG that needs them (charts.py
# and sections.py both consume rendering.sources per Tasks 12-13's own
# sanctioned DAG) — moved here instead to avoid a sources<->sections circular
# import; render_business_report.py imports `_numeric_suffix` back from here
# for its own remaining call sites. Record kept for Task 13's implementer.
_ID_NUM_RE = re.compile(r"[A-Za-z]+([1-9][0-9]*)$")


def _numeric_suffix(identifier: str) -> int:
    """Extracts the trailing number from an `F*`/`D*`/`S*`/`V*`/`FP*` id for
    sort keys. All such ids are already validated against their grammar
    upstream, so the match always succeeds in practice; the 0 fallback only
    guards a value that somehow bypassed validation, keeping sorting total
    rather than raising mid-render."""
    m = _ID_NUM_RE.match(identifier)
    return int(m.group(1)) if m else 0


def _sorted_by_numeric_id[T: Mapping[str, object]](items: Sequence[T]) -> list[T]:
    """Sorts a validated id-bearing list (sources, additional_sources, ...)
    by numeric id ascending — a document's own list order is otherwise
    whatever the LLM emitted, and the determinism contract (spec §7)
    requires every list reaching the HTML to be sorted. Generic over `T`
    (bound to `Mapping[str, object]`, satisfied by `AgentSource`,
    `VerificationAdditionalSource`, and any other `models.py` document
    TypedDict) so callers get back the same concrete item type they passed
    in, rather than a widened `Mapping`."""
    def _id_rank(item: Mapping[str, object]) -> int:
        identifier = item["id"]
        return _numeric_suffix(identifier) if isinstance(identifier, str) else 0
    return sorted(items, key=_id_rank)


def merged_sources(run: Run) -> list[MergedSource]:
    """Deduplicates every source the run relied on — panel sources and
    verifier `additional_sources` — by canonical URL (spec §7, §8 item 8).
    Mentions are folded in a fixed walk: roster order over each survivor's
    own panel sources first, then roster order again over each survivor's
    verifier `additional_sources`; within one document, sources are taken
    in ascending numeric-id order. The *first* mention encountered in that
    walk wins the merged entry's `title`/`publisher` (spec: "first by
    roster order wins" — every raw variant stays intact in the embedded
    provenance block). The returned list is sorted by canonical URL
    ascending — the renderer's own deterministic order for the appendix
    (spec §7)."""
    roster = [e for e in run.manifest.get("roster", []) if isinstance(e, dict)]
    groups: dict[str, _SourceGroup] = {}

    # Two distinct loop variables (not one reused `src`): each walk yields a
    # different models TypedDict (AgentSource / VerificationAdditionalSource),
    # and mypy correctly rejects redefining one variable across incompatible
    # TypedDict types now that Run's fields are concrete.
    for entry in roster:
        survivor = run.survivors[entry["id"]]
        reachability_by_id = {s["id"]: s["reachability"]
                               for s in survivor["verification"]["sources"]}
        for panel_src in _sorted_by_numeric_id(survivor["panel"]["sources"]):
            _fold_mention(groups, url=panel_src["url"], title=panel_src["title"],
                          publisher=panel_src["publisher"],
                          mention=SourceMention(origin="panel", agent=entry["id"],
                                                 local_id=panel_src["id"],
                                                 detail=panel_src["usage"],
                                                 reachability=reachability_by_id[panel_src["id"]]))

    for entry in roster:
        survivor = run.survivors[entry["id"]]
        for verif_src in _sorted_by_numeric_id(survivor["verification"]["additional_sources"]):
            _fold_mention(groups, url=verif_src["url"], title=verif_src["title"],
                          publisher=verif_src["publisher"],
                          mention=SourceMention(origin="verifier", agent=entry["id"],
                                                 local_id=verif_src["id"],
                                                 detail=verif_src["usage"],
                                                 reachability=None))

    used_anchors: set[str] = set()
    merged: list[MergedSource] = []
    for index, curl in enumerate(sorted(groups), start=1):
        group = groups[curl]
        merged.append(MergedSource(canonical_url=curl, title=group["title"],
                                    publisher=group["publisher"],
                                    mentions=tuple(group["mentions"]),
                                    anchor_id=_source_anchor_id(curl, index, used_anchors)))
    return merged


def render_sources(run: Run) -> str:
    """Sources appendix (spec §8 item 8): every `MergedSource` from
    `merged_sources`, already sorted by canonical URL ascending, each with
    every contributing agent's/verifier's own mention."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    entries = []
    for source in merged_sources(run):
        href = safe_url(source.canonical_url)
        title_html = (f'<a href="{esc(href)}">{esc(source.title)}</a>' if href
                      else esc(source.title))
        mention_items = "".join(_render_mention(m, labels) for m in source.mentions)
        entries.append(
            f'<div class="source-entry" id="{esc(source.anchor_id)}">'
            f'<p class="source-title">{title_html} — {esc(source.publisher)}</p>'
            f'<ul class="source-mentions">{mention_items}</ul>'
            "</div>"
        )
    return _wrap_section("sources", labels["sources"], "".join(entries))


def _fold_mention(groups: dict[str, _SourceGroup], *, url: str, title: str, publisher: str,
                   mention: SourceMention) -> None:
    """Folds one `SourceMention` into `groups` (keyed by canonical URL),
    used by `merged_sources` while walking panel sources and verifier
    `additional_sources` in a fixed order. The first call for a given
    canonical URL fixes that entry's `title`/`publisher` (spec: "first by
    roster order wins")."""
    curl = json_io.canonical_url(url)
    group = groups.get(curl)
    if group is None:
        group = {"title": title, "publisher": publisher, "mentions": []}
        groups[curl] = group
    group["mentions"].append(mention)


_ANCHOR_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _source_anchor_id(canonical_url: str, index: int, used: set[str]) -> str:
    """Deterministic per-source anchor id for the sources appendix (spec §8
    item 8): `src-<slug>`, where `<slug>` is the canonical URL lowercased
    with every run of non-`[a-z0-9]` characters collapsed to one hyphen and
    stripped from both ends. Falls back to `src-<1-based index in the
    sorted, already-deduplicated appendix>` if that slug is empty or
    collides with an id already produced in this render (e.g. two canonical
    URLs differing only in punctuation) — the index is always unique because
    `merged_sources` assigns it while walking its own sorted output."""
    slug = _ANCHOR_SLUG_RE.sub("-", canonical_url.lower()).strip("-")
    candidate = f"src-{slug}" if slug else ""
    if not candidate or candidate in used:
        candidate = f"src-{index}"
    used.add(candidate)
    return candidate


def _render_mention(mention: SourceMention, labels: Labels) -> str:
    """One `<li>` in a `MergedSource`'s mention list: its qualified id, an
    origin tag (found-by-verifier / reachability), and its usage detail
    text."""
    qualified = f"{mention.agent}:{mention.local_id}"
    if mention.origin == "verifier":
        tag = f'<span class="tag tag-verifier">{esc(labels["found_by_verifier"])}</span>'
    elif mention.reachability is not None:
        tag = (f'<span class="tag tag-reachability-{esc(mention.reachability)}">'
               f'{esc(labels["reachability"][mention.reachability])}</span>')
    else:
        tag = ""
    detail = esc(mention.detail) if mention.detail else ""
    return f"<li>{esc(qualified)} {tag} {detail}</li>"
