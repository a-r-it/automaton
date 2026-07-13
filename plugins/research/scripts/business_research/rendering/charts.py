"""Chart grouping and SVG rendering (V2 spec §8 items 4-5)."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, cast

from business_research.models import AgentDataPoint, AgentFinding
from business_research.rendering.localization import LABELS, _lang, _wrap_section, esc, fmt_num
from business_research.rendering.sources import MergedSource, _numeric_suffix, merged_sources

if TYPE_CHECKING:
    from business_research.rendering.report import Run


# Geometry constants: fixed `viewBox` (spec step 3) so `.chart-svg { width:
# 100%; height: auto; }` scales the drawing responsively without overflow
# (mobile check, §11) while every coordinate stays a deterministic function
# of the chart's own points -- never random, never wall-clock-derived.

KPI_STRIP_CAP = 8

_LINE_WIDTH = 640
_LINE_HEIGHT = 260
_LINE_MARGIN = {"left": 56, "right": 16, "top": 16, "bottom": 32}

_BAR_WIDTH = 640
_BAR_LABEL_WIDTH = 240
# "right" leaves room for the value label drawn just past a full-width bar
# (spec step 3 puts the value at the bar's end) — the SVG root defaults to
# `overflow: hidden`, so anything short here gets silently clipped rather
# than overflowing visibly; 56px comfortably fits values up to ~6 digits at
# the 10px label font size used throughout these charts.
_BAR_MARGIN = {"right": 56, "top": 16, "bottom": 32}
_BAR_ROW_HEIGHT = 24
_BAR_ROW_GAP = 12

_GRIDLINE_FRACTIONS = (0.0, 1 / 3, 2 / 3, 1.0)


class ChartPoint(AgentDataPoint):
    """One agent data point (spec §5 fields, inherited from
    `models.AgentDataPoint`) decorated with the rendering-only fields
    `_verified_chart_points` adds: `agent`, `entity_label`,
    `source_qualified`/`source_href` (the footer citation, `None` when
    unresolved), and — only once a bar-consuming pass (`_consume_bar_geo`/
    `_consume_bar_entity`) has claimed the point — `bar_label`. `bar_label`
    stays `NotRequired` rather than living on a bar-only subtype: `Chart`
    is shared by both kinds (spec: `kind` is `"line"` or `"bar"`), so a
    single `points` field type that's honest about "present only for bar
    charts" is simpler than a kind-discriminated union here."""

    agent: str
    entity_label: str
    source_qualified: str | None
    source_href: str | None
    bar_label: NotRequired[str]


@dataclass(frozen=True)
class Chart:
    """One deterministic SVG chart (spec §8 item 5, chart-compatibility
    rules), produced by `group_charts` from a single agent's verified
    data points. `kind` is `"line"` or `"bar"`. `label` is a ready-to-escape
    display heading built from the group's held-fixed dimensions (metric,
    unit, and whichever of period/geography stayed fixed for this group).
    `points` are the group's own decorated point dicts (spec §5 fields plus
    `agent`, `entity_label`, `source_qualified`/`source_href` — see
    `_verified_chart_points` — and, for bar charts, `bar_label`), already
    ordered by `group_charts`: line by period ascending, bar by row label
    ascending, both tie-broken by data point id."""

    kind: str
    label: str
    points: tuple[ChartPoint, ...]


def group_charts(points: list[ChartPoint]) -> tuple[list[Chart], list[ChartPoint]]:
    """Groups one agent's verified data points into deterministic charts
    (spec §8 item 5, chart-compatibility rules), each point consumed at most
    once. Three precedence passes, each fully consuming its own matches
    before the next pass sees what's left:

      1. line: same (`metric`, `unit`, `geography`), >=3 `period` values,
         every member's period *pairwise distinct* (point count ==
         distinct-period count) — a group with a repeated period is left
         completely untouched for this pass and falls through to the bar
         passes / leftover cards (parity with the bar-geo rule below).
      2. bar-geo: same (`metric`, `unit`, `period`), varying `geography` —
         eligible only when every member's geography is *pairwise
         distinct* (point count == distinct-geography count, and that
         count is >=2); a group with a repeated geography is left
         completely untouched for this pass (not consumed, not even the
         non-repeated members) and falls through to bar-entity, which
         holds geography fixed too — so a same-geography subset can still
         form a bar-entity group there (spec §8, decision amendment).
      3. bar-entity: same (`metric`, `unit`, `period`, `geography`), >=2
         points; row label = each point's pre-computed `entity_label`
         (spec: first 40 chars of the linked finding's claim, else the
         D-id — see `_entity_label`; this function only reads the field,
         it does no finding lookups of its own, which is what keeps it
         testable on bare dict literals).

    **Negative values are never charted** (spec §8, decision amendment):
    each pass additionally skips any candidate group containing a member
    with `value < 0` — the whole group is left unconsumed rather than
    partially formed, so every one of its points falls through to the next
    pass (and, if nothing downstream claims it either, ends up a leftover
    card showing the true signed number via `fmt_num`).

    Grouping keys use exact string equality on the held-fixed dimensions —
    no unit/metric alias normalization (spec §12: out of scope; a
    near-miss degrades to a card, never a wrong chart). Returns
    `(charts, leftover)`: `leftover` is every point no pass consumed, in
    input order. `charts` is ordered by (metric, unit, label) ascending —
    deterministic even when one agent produces more than one chart;
    ordering *across* agents is the caller's job (roster order)."""
    charts: list[Chart] = []
    remaining = list(points)
    for consume in (_consume_line, _consume_bar_geo, _consume_bar_entity):
        found, remaining = consume(remaining)
        charts.extend(found)
    charts.sort(key=lambda c: (c.points[0]["metric"], c.points[0]["unit"], c.label))
    return charts, remaining


def svg_line(chart: Chart, lang: str) -> str:
    """Renders a line-kind `Chart` as a self-contained, theme-safe SVG (spec
    §8: fixed `viewBox`, no random ids, `currentColor`/CSS-var colors only).
    X-axis: `chart.points`' `period` values, evenly spaced in the order
    `group_charts` already sorted them. Y-axis: 0 at the bottom, `max(value)`
    at the top (spec step 3: "max(value) scaling"), 4 gridlines (spec step
    3) labelled via `fmt_num`. Each point is its own
    `<circle id="dp-<agent>-D<n>">` — the anchor narrative D-refs resolve
    to (spec: "Each data point card/chart node gets id=...")."""
    m = _LINE_MARGIN
    plot_x0, plot_x1 = m["left"], _LINE_WIDTH - m["right"]
    plot_y0, plot_y1 = m["top"], _LINE_HEIGHT - m["bottom"]
    points = chart.points
    periods = [p["period"] for p in points]
    max_value = max((p["value"] for p in points), default=0)
    max_value = max_value if max_value > 0 else 1

    def x_of(period: str) -> float:
        n = len(periods)
        idx = periods.index(period)
        return plot_x0 if n <= 1 else plot_x0 + (idx / (n - 1)) * (plot_x1 - plot_x0)

    def y_of(value: float) -> float:
        frac = max(0.0, value) / max_value
        return plot_y1 - frac * (plot_y1 - plot_y0)

    gridlines = []
    for frac in _GRIDLINE_FRACTIONS:
        y = plot_y1 - frac * (plot_y1 - plot_y0)
        gridlines.append(
            f'<line x1="{plot_x0}" y1="{y:.1f}" x2="{plot_x1}" y2="{y:.1f}" '
            'stroke="var(--color-border)" stroke-width="1"/>'
            f'<text x="{plot_x0 - 8}" y="{y:.1f}" text-anchor="end" '
            'dominant-baseline="middle" font-size="10" fill="currentColor">'
            f"{esc(fmt_num(frac * max_value, lang))}</text>"
        )

    polyline_points = " ".join(f"{x_of(p['period']):.1f},{y_of(p['value']):.1f}" for p in points)
    dots = []
    for p in points:
        x, y = x_of(p["period"]), y_of(p["value"])
        anchor = f"dp-{p['agent']}-{p['id']}"
        dots.append(
            f'<circle id="{esc(anchor)}" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="currentColor">'
            f"<title>{esc(p['period'])}: {esc(fmt_num(p['value'], lang))} {esc(p['unit'])}</title>"
            "</circle>"
            f'<text x="{x:.1f}" y="{plot_y1 + 16}" text-anchor="middle" font-size="10" '
            f'fill="currentColor">{esc(p["period"])}</text>'
        )

    body = "".join(gridlines) + (
        f'<polyline points="{polyline_points}" fill="none" stroke="currentColor" '
        'stroke-width="2"/>'
    ) + "".join(dots)

    return (
        '<div class="chart chart-line">'
        f'<p class="chart-title">{esc(chart.label)}</p>'
        f'<svg class="chart-svg" viewBox="0 0 {_LINE_WIDTH} {_LINE_HEIGHT}" '
        f'role="img" aria-label="{esc(chart.label)}">{body}</svg>'
        f"{_chart_footer(points, lang)}"
        "</div>"
    )


def svg_bar(chart: Chart, lang: str) -> str:
    """Renders a bar-kind `Chart` (bar-geo or bar-entity — both share the
    same `kind`, spec §8) as a self-contained, theme-safe horizontal-bar SVG.
    Row height is a fixed 24px (spec step 3), viewBox height grows
    deterministically with the row count. Value axis: 0 at the label edge,
    `max(value)` at the far edge, 4 gridlines (spec step 3). Each bar is its
    own `<rect id="dp-<agent>-D<n>">` for D-ref anchoring."""
    points = chart.points
    n = len(points)
    height = _BAR_MARGIN["top"] + n * _BAR_ROW_HEIGHT + max(0, n - 1) * _BAR_ROW_GAP \
        + _BAR_MARGIN["bottom"]
    plot_x0, plot_x1 = _BAR_LABEL_WIDTH, _BAR_WIDTH - _BAR_MARGIN["right"]
    baseline_y = _BAR_MARGIN["top"] + n * _BAR_ROW_HEIGHT + max(0, n - 1) * _BAR_ROW_GAP
    max_value = max((p["value"] for p in points), default=0)
    max_value = max_value if max_value > 0 else 1

    def width_of(value: float) -> float:
        frac = max(0.0, value) / max_value
        return frac * (plot_x1 - plot_x0)

    gridlines = []
    for frac in _GRIDLINE_FRACTIONS:
        x = plot_x0 + frac * (plot_x1 - plot_x0)
        gridlines.append(
            f'<line x1="{x:.1f}" y1="{_BAR_MARGIN["top"] - 4}" x2="{x:.1f}" '
            f'y2="{baseline_y}" stroke="var(--color-border)" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{baseline_y + 16}" text-anchor="middle" font-size="10" '
            f'fill="currentColor">{esc(fmt_num(frac * max_value, lang))}</text>'
        )

    bars = []
    for i, p in enumerate(points):
        y = _BAR_MARGIN["top"] + i * (_BAR_ROW_HEIGHT + _BAR_ROW_GAP)
        w = width_of(p["value"])
        anchor = f"dp-{p['agent']}-{p['id']}"
        row_center = y + _BAR_ROW_HEIGHT / 2
        bars.append(
            f'<rect id="{esc(anchor)}" x="{plot_x0}" y="{y}" width="{w:.1f}" '
            f'height="{_BAR_ROW_HEIGHT}" fill="currentColor">'
            f"<title>{esc(p['bar_label'])}: {esc(fmt_num(p['value'], lang))} "
            f"{esc(p['unit'])}</title></rect>"
            f'<text x="{plot_x0 - 8}" y="{row_center:.1f}" text-anchor="end" '
            f'dominant-baseline="middle" font-size="10" fill="currentColor">'
            f"{esc(p['bar_label'])}</text>"
            f'<text x="{plot_x0 + w + 6:.1f}" y="{row_center:.1f}" '
            f'dominant-baseline="middle" font-size="10" fill="currentColor">'
            f"{esc(fmt_num(p['value'], lang))}</text>"
        )

    body = "".join(gridlines) + "".join(bars)
    return (
        '<div class="chart chart-bar">'
        f'<p class="chart-title">{esc(chart.label)}</p>'
        f'<svg class="chart-svg" viewBox="0 0 {_BAR_WIDTH} {height}" '
        f'role="img" aria-label="{esc(chart.label)}">{body}</svg>'
        f"{_chart_footer(points, lang)}"
        "</div>"
    )


def kpi_card(point: ChartPoint, lang: str) -> str:
    """Renders one verified data point as a stand-alone card (spec §8: "KPI
    card: any verified data point not consumed by a chart") — used both for
    the top-level KPI strip (item 4) and for an agent's own leftover data
    points that didn't make the strip's cap (item 5). Carries the same
    `id="dp-<agent>-D<n>"` anchor scheme as chart points, so a D-ref
    resolves the same way regardless of which of the two places rendered
    it."""
    labels = LABELS[lang]
    anchor = f"dp-{point['agent']}-{point['id']}"
    dims = f'{esc(point["period"])} · {esc(point["geography"])}'
    qualified = point.get("source_qualified")
    footer = ""
    if qualified:
        href = point.get("source_href")
        source_html = f'<a href="#{esc(href)}">{esc(qualified)}</a>' if href else esc(qualified)
        footer = f'<p class="kpi-footer">{esc(labels["sources"])}: {source_html}</p>'
    return (
        f'<div class="kpi-card" id="{esc(anchor)}">'
        f'<p class="kpi-metric">{esc(point["metric"])}</p>'
        f'<p class="kpi-value">{esc(fmt_num(point["value"], lang))} {esc(point["unit"])}</p>'
        f'<p class="kpi-dims">{dims}</p>'
        f"{footer}"
        "</div>"
    )


def render_kpi_strip(run: Run) -> str:
    """Top-level KPI strip (spec §8 item 4): a capped, deterministic,
    cross-agent highlight reel of "top verified data points as cards".
    Selection: `_global_kpi_pool` already orders every agent's
    *un-charted* verified data points by (roster order, then D-id) — the
    first `KPI_STRIP_CAP` of that pool are "top" by that same order.
    Charted data points never appear here; they're already visualized in
    their own agent's section (spec §8 item 5)."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    strip_points = _global_kpi_pool(run)[:KPI_STRIP_CAP]
    body = "\n".join(kpi_card(point, lang) for point in strip_points)
    return _wrap_section("kpi-strip", labels["kpi_strip"], body)


def _group_by[T, K](items: Sequence[T], key_fn: Callable[[T], K]) -> list[tuple[K, list[T]]]:
    """Partitions `items` by `key_fn`, preserving first-seen key order — the
    stable base every `group_charts` precedence pass groups from. Generic
    over both the item type `T` and the key type `K` so every one of the
    three precedence passes below gets back its own concrete
    `(metric, unit, ...)` tuple type rather than a widened bare `tuple`."""
    groups: dict[K, list[T]] = {}
    order: list[K] = []
    for item in items:
        key = key_fn(item)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    return [(key, groups[key]) for key in order]


def _consume_line(remaining: list[ChartPoint]) -> tuple[list[Chart], list[ChartPoint]]:
    """`group_charts` precedence 1: same (metric, unit, geography), >=3
    *pairwise-distinct* `period` values → one line chart per qualifying
    group, points sorted period ascending (tie-broken by id). A group with
    a repeated period is left fully unconsumed (spec §8 amendment, parity
    with bar-geo's pairwise-distinct-geography rule): duplicate periods
    would collapse onto one x position, so the whole group falls through
    to the later passes (and, if nothing downstream claims it, to leftover
    cards) rather than forming a misleading line. A group containing any
    member with `value < 0` is likewise skipped entirely (spec §8
    amendment: negative values are never charted)."""
    charts: list[Chart] = []
    consumed: set[str] = set()
    for (metric, unit, geography), members in _group_by(
            remaining, lambda p: (p["metric"], p["unit"], p["geography"])):
        periods = [p["period"] for p in members]
        distinct_periods = set(periods)
        if len(distinct_periods) < 3 or len(distinct_periods) != len(periods):
            continue
        if any(p["value"] < 0 for p in members):
            continue
        ordered = sorted(members, key=lambda p: (p["period"], _numeric_suffix(p["id"])))
        charts.append(Chart(kind="line", label=f"{metric} · {unit} · {geography}",
                             points=tuple(ordered)))
        consumed.update(p["id"] for p in members)
    return charts, [p for p in remaining if p["id"] not in consumed]


def _consume_bar_geo(remaining: list[ChartPoint]) -> tuple[list[Chart], list[ChartPoint]]:
    """`group_charts` precedence 2: same (metric, unit, period), varying
    `geography` → one bar chart per qualifying group, rows labelled by
    geography, sorted label ascending (tie-broken by id). Eligible only
    when every member's geography is *pairwise distinct* — point count
    equal to distinct-geography count, and that count >=2 (spec §8
    amendment). A group with a repeated geography is left fully unconsumed
    here (not just the duplicate) so it falls through untouched to
    bar-entity, which holds geography fixed and can still chart a
    same-geography subset of it. A group containing any member with
    `value < 0` is likewise skipped entirely (negative values are never
    charted)."""
    charts: list[Chart] = []
    consumed: set[str] = set()
    for (metric, unit, period), members in _group_by(
            remaining, lambda p: (p["metric"], p["unit"], p["period"])):
        geographies = [p["geography"] for p in members]
        distinct_geographies = set(geographies)
        if len(distinct_geographies) < 2 or len(distinct_geographies) != len(geographies):
            continue
        if any(p["value"] < 0 for p in members):
            continue
        decorated: list[ChartPoint] = [{**p, "bar_label": p["geography"]} for p in members]
        ordered = sorted(decorated, key=lambda p: (p["bar_label"], _numeric_suffix(p["id"])))
        charts.append(Chart(kind="bar", label=f"{metric} · {unit} · {period}",
                             points=tuple(ordered)))
        consumed.update(p["id"] for p in members)
    return charts, [p for p in remaining if p["id"] not in consumed]


def _consume_bar_entity(remaining: list[ChartPoint]) -> tuple[list[Chart], list[ChartPoint]]:
    """`group_charts` precedence 3: same (metric, unit, period, geography),
    >=2 points → one bar chart per qualifying group, rows labelled by each
    point's pre-computed `entity_label`, sorted label ascending (tie-broken
    by id). A group containing any member with `value < 0` is skipped
    entirely (spec §8 amendment: negative values are never charted)."""
    charts: list[Chart] = []
    consumed: set[str] = set()
    for (metric, unit, period, geography), members in _group_by(
            remaining, lambda p: (p["metric"], p["unit"], p["period"], p["geography"])):
        if len(members) < 2:
            continue
        if any(p["value"] < 0 for p in members):
            continue
        decorated: list[ChartPoint] = [{**p, "bar_label": p["entity_label"]} for p in members]
        ordered = sorted(decorated, key=lambda p: (p["bar_label"], _numeric_suffix(p["id"])))
        charts.append(Chart(kind="bar", label=f"{metric} · {unit} · {period} · {geography}",
                             points=tuple(ordered)))
        consumed.update(p["id"] for p in members)
    return charts, [p for p in remaining if p["id"] not in consumed]


def _chart_footer(points: tuple[ChartPoint, ...], lang: str) -> str:
    """Shared chart-footer builder (spec: "every chart/card footer cites
    qualified source ids"): every distinct `<agent>:S<n>` among the
    chart's own points, first-seen order, linked into the sources appendix
    when a `source_href` was resolved (`_verified_chart_points`), else
    shown as plain escaped text. Points with no external source (a
    hypothetical `calculated` data point with an empty `source_id`) are
    silently skipped — nothing to cite."""
    labels = LABELS[lang]
    seen: set[str] = set()
    entries: list[str] = []
    for p in points:
        qualified = p.get("source_qualified")
        if not qualified or qualified in seen:
            continue
        seen.add(qualified)
        href = p.get("source_href")
        entries.append(f'<a href="#{esc(href)}">{esc(qualified)}</a>' if href else esc(qualified))
    if not entries:
        return ""
    return f'<p class="chart-footer">{esc(labels["sources"])}: {", ".join(entries)}</p>'


def _entity_label(data_point_id: str, findings: list[AgentFinding]) -> str:
    """Bar-entity chart row label (spec §8 chart-compatibility, bar-entity
    variant): the first 40 characters of the claim of the finding whose
    `data_point_ids` includes this data point, choosing the lowest-numbered
    finding id when more than one links to the same point (deterministic
    tie-break); falls back to the data point's own id when no finding links
    to it. `findings` must already be filtered to that agent's
    *verified* findings by the caller (`_verified_chart_points`) — this
    function does no verdict lookups of its own (keeps it testable on bare
    dict literals), so a finding excluded from `findings` behaves exactly
    like one that never linked to the point: an unverified-only link falls
    back to the D-id label, it never wins the row label."""
    linking = sorted((f for f in findings if data_point_id in f.get("data_point_ids", [])),
                      key=lambda f: _numeric_suffix(f["id"]))
    return linking[0]["claim"][:40] if linking else data_point_id


def _verified_chart_points(run: Run, agent_id: str) -> list[ChartPoint]:
    """Every *verified* data point of one agent's surviving attempt
    (spec §8 item 5 eligibility: drawn from the verification lookup, never
    the raw panel list), sorted by D-id ascending — the deterministic base
    order `group_charts` groups from. Each point is the panel document's own
    data-point dict plus the fields the chart/card renderers need but that
    aren't part of the wire schema: `agent`, `entity_label` (§8
    bar-entity rule — looked up only among this agent's *verified*
    findings, per the same verification lookup as the data points
    themselves; a finding that is the sole link to a data point but wasn't
    itself verified must not win the row label, so it's filtered out
    before `_entity_label` ever sees it), and `source_qualified`/
    `source_href` (the footer citation, resolved once here against the
    run's own merged-sources anchor map so
    `group_charts`/`svg_line`/`svg_bar`/`kpi_card` never need the run or
    the anchor map as a parameter)."""
    survivor = run.survivors[agent_id]
    panel = survivor["panel"]
    verification = survivor["verification"]
    anchors = _qualified_source_anchors(merged_sources(run))
    verified_ids = {d["id"] for d in verification["data_points"] if d["verdict"] == "verified"}
    verified_finding_ids = {f["id"] for f in verification["findings"] if f["verdict"] == "verified"}
    verified_findings = [f for f in panel["findings"] if f["id"] in verified_finding_ids]
    dp_by_id: dict[str, AgentDataPoint] = {d["id"]: d for d in panel["data_points"]}
    points: list[ChartPoint] = []
    for did in sorted(verified_ids, key=_numeric_suffix):
        dp = dp_by_id[did]
        source_id = dp.get("source_id") or ""
        source_qualified = f"{agent_id}:{source_id}" if source_id else None
        # cast: mypy's TypedDict-unpack completeness check treats a
        # NotRequired key (`bar_label`) as unaccounted-for unless the `**`
        # source's own declared type also carries it. `dp` is
        # `AgentDataPoint`, which never declares `bar_label` — it's added
        # only later, by `_consume_bar_geo`/`_consume_bar_entity`. Every
        # `ChartPoint`-required key IS present (all of `AgentDataPoint` via
        # `**dp`, the four rendering-only fields via the literal below);
        # `bar_label` is correctly, intentionally absent at this point in
        # the pipeline — this is a known mypy limitation, not a missing
        # field.
        points.append(cast(ChartPoint, {
            **dp,
            "agent": agent_id,
            "entity_label": _entity_label(did, verified_findings),
            "source_qualified": source_qualified,
            "source_href": anchors.get(source_qualified) if source_qualified else None,
        }))
    return points


def _global_kpi_pool(run: Run) -> list[ChartPoint]:
    """Deterministic (roster order, then D-id) flat list of every verified
    data point *not* consumed by its own agent's charts, across the
    whole run. The first `KPI_STRIP_CAP` of this list is the top-level KPI
    strip (spec §8 item 4); the rest render as leftover cards inside their
    own agent's section (spec §8 item 5). This split is what keeps every
    verified data point's `id="dp-<agent>-D<n>"` anchor unique across the
    document — a chart-consumed point renders once, inside its chart; an
    un-charted point renders once, either in the strip or in its own
    section, never both (`render_kpi_strip` and `render_section` both slice
    this same ordered list, so the cut is consistent everywhere it's read).
    Pure function of `run`: safe to call from more than one render_* site,
    same pattern this module already uses for `merged_sources`."""
    roster = [e for e in run.manifest.get("roster", []) if isinstance(e, dict)]
    pool: list[ChartPoint] = []
    for entry in roster:
        pid = entry["id"]
        if pid not in run.survivors:
            continue
        _charts, leftover = group_charts(_verified_chart_points(run, pid))
        pool.extend(leftover)
    return pool


def _qualified_source_anchors(merged: list[MergedSource]) -> dict[str, str]:
    """Maps every panel-origin mention's qualified id (`'<agent>:S<n>'`)
    to its `MergedSource` anchor id. Shared by `_verified_chart_points`
    here and by `render_section` (still in `render_business_report.py`,
    due to move in Task 13) — kept in this module rather than the renderer
    because charts.py's own DAG (sources + localization + models, see
    Task 12) already sanctions depending on `MergedSource`, whereas the
    renderer importing back from charts.py for its own remaining call site
    mirrors the established `_numeric_suffix`/sources.py precedent (Task
    11) rather than introducing a charts->renderer edge."""
    return {f"{mention.agent}:{mention.local_id}": source.anchor_id
            for source in merged for mention in source.mentions
            if mention.origin == "panel"}
