"""Narrative report sections (V2 spec §8)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from business_research.rendering.charts import (
    KPI_STRIP_CAP,
    _global_kpi_pool,
    _qualified_source_anchors,
    _verified_chart_points,
    group_charts,
    kpi_card,
    svg_bar,
    svg_line,
)
from business_research.rendering.localization import LABELS, _lang, _wrap_section, esc, fmt_num
from business_research.rendering.sources import _numeric_suffix, merged_sources

if TYPE_CHECKING:
    from business_research.rendering.report import Run


# Renderer-owned section headings per roster id (spec §8 table, verbatim).
HEADINGS: dict[str, dict[str, str]] = {
    "market-researcher": {"ru": "Рынок", "en": "Market"},
    "product-manager": {"ru": "Продукт", "en": "Product"},
    "business-analyst": {"ru": "Бизнес-модель", "en": "Business model"},
    "trend-analyst": {"ru": "Тренды и тайминг", "en": "Trends and timing"},
    "competitive-analyst": {"ru": "Конкуренция и защитимость",
                             "en": "Competition and moat"},
    "risk-manager": {"ru": "Риски и сценарии провала",
                      "en": "Risks and failure modes"},
    "pricing-monetization": {"ru": "Ценообразование и монетизация",
                              "en": "Pricing and monetization"},
    "gtm-channels": {"ru": "Каналы и дистрибуция",
                      "en": "Go-to-market and channels"},
    "unit-economics": {"ru": "Юнит-экономика", "en": "Unit economics"},
    "legal-advisor": {"ru": "Регуляторика и комплаенс",
                       "en": "Regulatory and compliance"},
    "ux-researcher": {"ru": "Клиентские инсайты", "en": "Customer insights"},
    "project-idea-validator": {"ru": "Валидация идеи", "en": "Idea validation"},
}


def render_exec_summary(run: Run, dp_anchors: frozenset[str]) -> str:
    """Executive summary (spec §8 item 2): verdict statement first (Minto
    pyramid — the header badge only shows the decision label, this is the
    full sentence), then the synthesizer's `executive_summary` paragraphs,
    each with its refs rendered as superscript trace markers."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    verdict = run.synthesis["verdict"]
    decision_label = labels["verdict_decision"].get(verdict["decision"], verdict["decision"])
    parts = [
        f'<p class="verdict-statement"><strong>{esc(decision_label)}:</strong> '
        f'{esc(verdict["statement"])}{_render_refs(verdict["refs"], dp_anchors)}</p>'
    ]
    for item in run.synthesis["executive_summary"]:
        parts.append(f'<p>{esc(item["text"])}{_render_refs(item["refs"], dp_anchors)}</p>')
    return _wrap_section("exec-summary", labels["executive_summary"], "".join(parts))


def render_methodology(run: Run) -> str:
    """Renderer-generated methodology (spec §8 item 3): built only from the
    manifest + staged records, never from LLM prose — a roster table (id,
    model, selection rule), source/finding/data-point counters, and
    verification stats ("X of Y verified"), all localized via `LABELS`."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    roster = [e for e in run.manifest.get("roster", []) if isinstance(e, dict)]

    rows: list[str] = []
    total_sources = total_findings = total_data_points = 0
    total_findings_verif = total_data_points_verif = 0
    verified_findings = verified_data_points = 0
    for entry in roster:
        survivor = run.survivors[entry["id"]]
        panel = survivor["panel"]
        verification = survivor["verification"]
        rows.append(
            "<tr>"
            f"<td>{esc(entry['id'])}</td>"
            f"<td>{esc(entry['model'])}</td>"
            f"<td>{esc(entry['selection_rule'])}</td>"
            "</tr>"
        )
        total_sources += len(panel["sources"])
        total_findings += len(panel["findings"])
        total_data_points += len(panel["data_points"])
        total_findings_verif += len(verification["findings"])
        total_data_points_verif += len(verification["data_points"])
        verified_findings += sum(1 for f in verification["findings"] if f["verdict"] == "verified")
        verified_data_points += sum(1 for d in verification["data_points"]
                                     if d["verdict"] == "verified")

    table = (
        '<table class="methodology-roster"><thead><tr>'
        f"<th>{esc(labels['methodology_col_id'])}</th>"
        f"<th>{esc(labels['methodology_col_model'])}</th>"
        f"<th>{esc(labels['methodology_col_selection_rule'])}</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    verified_findings_text = labels["methodology_verified_findings"].format(
        verified=fmt_num(verified_findings, lang), total=fmt_num(total_findings_verif, lang))
    verified_data_points_text = labels["methodology_verified_data_points"].format(
        verified=fmt_num(verified_data_points, lang), total=fmt_num(total_data_points_verif, lang))
    counts = (
        '<ul class="methodology-counts">'
        f"<li>{esc(labels['methodology_count_sources'])}: {fmt_num(total_sources, lang)}</li>"
        f"<li>{esc(labels['methodology_count_findings'])}: {fmt_num(total_findings, lang)}</li>"
        f"<li>{esc(labels['methodology_count_data_points'])}: "
        f"{fmt_num(total_data_points, lang)}</li>"
        f"<li>{esc(verified_findings_text)}</li>"
        f"<li>{esc(verified_data_points_text)}</li>"
        "</ul>"
    )

    body = f"<p>{esc(labels['methodology_pipeline'])}</p>{table}{counts}"
    return _wrap_section("methodology", labels["methodology"], body)


def render_section(run: Run, panelist_id: str, dp_anchors: frozenset[str]) -> str:
    """One per-angle section (spec §8 item 5): synthesizer narrative, then
    this panelist's own charts (from `group_charts`) plus whichever of its
    verified data points didn't make the top-level KPI strip (spec:
    "charts/KPI cards from that panelist's verified data_points" —
    `_global_kpi_pool` guarantees every one of them renders exactly once,
    either here or in the strip), then the findings list filtered to
    *verified* findings only (unsupported/contradicted findings are the
    renderer-generated drop entries in `render_limitations`, never shown
    here as if they were credible), each with a confidence badge and links
    to its own qualified sources in the appendix, then disagreement
    callouts."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    survivor = run.survivors[panelist_id]
    panel = survivor["panel"]
    verification = survivor["verification"]
    synth_section = next(s for s in run.synthesis["sections"] if s["panelist"] == panelist_id)
    anchors = _qualified_source_anchors(merged_sources(run))

    narrative = "".join(
        f'<p>{esc(item["text"])}{_render_refs(item["refs"], dp_anchors)}</p>'
        for item in synth_section["narrative"]
    )

    charts, leftover = group_charts(_verified_chart_points(run, panelist_id))
    strip_keys = {(p["panelist"], p["id"]) for p in _global_kpi_pool(run)[:KPI_STRIP_CAP]}
    section_cards = [p for p in leftover if (p["panelist"], p["id"]) not in strip_keys]
    # One block (chart or card) per line: keeps the section-charts area
    # diff-friendly in the goldens and lets a plain `grep -c "<svg"` count
    # distinct charts (test contract) instead of matching lines, since the
    # rest of this renderer's output is otherwise unbroken single-line HTML.
    blocks = [svg_line(c, lang) if c.kind == "line" else svg_bar(c, lang) for c in charts]
    blocks.extend(kpi_card(p, lang) for p in section_cards)
    blocks_joined = "\n".join(blocks)
    charts_block = f'\n<div class="section-charts">{blocks_joined}</div>' if blocks else ""

    verified_ids = {f["id"] for f in verification["findings"] if f["verdict"] == "verified"}
    findings = sorted((f for f in panel["findings"] if f["id"] in verified_ids),
                       key=lambda f: _numeric_suffix(f["id"]))
    finding_blocks = []
    for finding in findings:
        confidence = finding["confidence"]
        source_links = ", ".join(
            f'<a href="#{esc(anchors[f"{panelist_id}:{sid}"])}">{esc(f"{panelist_id}:{sid}")}</a>'
            for sid in finding["source_ids"]
        )
        finding_blocks.append(
            f'<div class="finding" id="finding-{esc(panelist_id)}-{esc(finding["id"])}">'
            f'<span class="confidence-badge confidence-{esc(confidence)}">'
            f'{esc(labels["confidence"][confidence])}</span>'
            f'<p class="finding-claim">{esc(finding["claim"])}</p>'
            f'<p class="finding-sources">{esc(labels["sources"])}: {source_links}</p>'
            "</div>"
        )

    disagreements = "".join(
        f'<div class="disagreement-callout"><strong>{esc(labels["disagreements"])}:</strong> '
        f'{esc(item["text"])}{_render_refs(item["refs"], dp_anchors)}</div>'
        for item in synth_section["disagreements"]
    )

    body = narrative + charts_block + "".join(finding_blocks) + disagreements
    return _wrap_section(f"section-{panelist_id}", HEADINGS[panelist_id][lang], body)


def render_risks(run: Run, dp_anchors: frozenset[str]) -> str:
    """Risks (spec §8 item 6), severity-sorted high→medium→low, stable
    within severity by input order (Python's `sorted` is stable, so a single
    sort keyed on severity rank alone is enough)."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    risks = sorted(run.synthesis["risks"], key=lambda r: _SEVERITY_RANK[r["severity"]])
    items = "".join(
        '<div class="risk-item">'
        f'<span class="severity-badge severity-{esc(r["severity"])}">'
        f'{esc(labels["severity"][r["severity"]])}</span>'
        f'<p>{esc(r["risk"])}{_render_refs(r["refs"], dp_anchors)}</p>'
        "</div>"
        for r in risks
    )
    return _wrap_section("risks", labels["risks"], items)


def render_recommendations(run: Run, dp_anchors: frozenset[str]) -> str:
    """Recommendations (spec §8 item 7), input order — no sort rule."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    items = "".join(
        f'<p>{esc(rec["recommendation"])}{_render_refs(rec["refs"], dp_anchors)}</p>'
        for rec in run.synthesis["recommendations"]
    )
    return _wrap_section("recommendations", labels["recommendations"], items)


def render_limitations(run: Run, dp_anchors: frozenset[str]) -> str:
    """Limitations (spec §8 item 9): the synthesizer's own `limitations`
    entries, plus renderer-generated drop entries built straight from the
    verification records — every unsupported/contradicted finding and data
    point, and every blocked/dead source — present even if the synthesizer
    never mentioned them (§5.3: those items never reach synthesis at all)."""
    lang = _lang(run.manifest)
    labels = LABELS[lang]
    roster = [e for e in run.manifest.get("roster", []) if isinstance(e, dict)]

    synthesis_items = "".join(
        f'<p>{esc(item["text"])}{_render_refs(item["refs"], dp_anchors)}</p>'
        for item in run.synthesis["limitations"]
    )

    drops: list[str] = []
    for entry in roster:
        pid = entry["id"]
        verification = run.survivors[pid]["verification"]
        for f in sorted(verification["findings"], key=lambda f: _numeric_suffix(f["id"])):
            if f["verdict"] == "unsupported":
                drops.append(_render_drop(labels["dropped_finding_unsupported"], pid, f["id"]))
            elif f["verdict"] == "contradicted":
                drops.append(_render_drop(labels["dropped_finding_contradicted"], pid, f["id"]))
        for d in sorted(verification["data_points"], key=lambda d: _numeric_suffix(d["id"])):
            if d["verdict"] == "unsupported":
                drops.append(_render_drop(labels["dropped_data_point_unsupported"], pid, d["id"]))
            elif d["verdict"] == "contradicted":
                drops.append(_render_drop(labels["dropped_data_point_contradicted"], pid, d["id"]))
        for s in sorted(verification["sources"], key=lambda s: _numeric_suffix(s["id"])):
            if s["reachability"] == "blocked":
                drops.append(_render_drop(labels["dropped_source_blocked"], pid, s["id"]))
            elif s["reachability"] == "dead":
                drops.append(_render_drop(labels["dropped_source_dead"], pid, s["id"]))

    drops_html = ""
    if drops:
        drops_html = (
            f'<p class="limitations-drops-heading">'
            f'{esc(labels["limitations_verification_drops"])}</p>'
            '<ul class="limitations-drops">' + "".join(f"<li>{d}</li>" for d in drops) + "</ul>"
        )

    return _wrap_section("limitations", labels["limitations"], synthesis_items + drops_html)


_REF_PATTERN = re.compile(r"^(?P<pid>[^:]+):(?P<kind>F|D)(?P<num>[1-9][0-9]*)$")


def _render_ref(ref: object, dp_anchors: frozenset[str]) -> str:
    """Renders one synthesis ref (`'<panelist>:F<n>'` / `'<panelist>:D<n>'`)
    as a superscript-style trace marker (spec §8 item 5). `F`-refs link to
    that finding's own anchor in its per-angle section
    (`id="finding-<panelist>-F<n>"`, emitted by `render_section`) — every
    `F`-ref reaching here was already proven by `validate_synthesis` to
    resolve to a *verified* finding of a surviving panelist, and
    `render_section` renders exactly that set, so the anchor always exists,
    unconditionally. `D`-refs link to `id="dp-<panelist>-D<n>"` (a chart
    point, a KPI-strip card, or a per-section leftover card — see
    `_global_kpi_pool`) *when the target exists*: `dp_anchors` (built once
    by `_all_dp_anchor_ids`) is the full set of ids this render will
    actually produce, checked explicitly rather than assumed like the
    `F`-ref case — cheap insurance against the chart/KPI-strip layer ever
    dropping a verified data point on the floor."""
    if not isinstance(ref, str):
        return f'<sup class="ref">{esc(ref)}</sup>'
    m = _REF_PATTERN.match(ref)
    if m is None:
        return f'<sup class="ref">{esc(ref)}</sup>'
    pid, kind, num = m.group("pid"), m.group("kind"), m.group("num")
    label = esc(f"{pid}:{kind}{num}")
    if kind == "F":
        return f'<sup class="ref"><a href="#finding-{esc(pid)}-F{num}">{label}</a></sup>'
    anchor = f"dp-{pid}-D{num}"
    if anchor in dp_anchors:
        return f'<sup class="ref"><a href="#{esc(anchor)}">{label}</a></sup>'
    return f'<sup class="ref">{label}</sup>'


def _render_refs(refs: Sequence[object], dp_anchors: frozenset[str]) -> str:
    # Sequence, not list: covariant, so the concrete list[SynthesisRef]
    # (= list[str]) every SynthesisDoc refs field now carries is accepted
    # without widening — list[str] is not a list[object] under invariance.
    return "".join(_render_ref(ref, dp_anchors) for ref in refs)


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _render_drop(template: str, panelist: str, item_id: str) -> str:
    """One renderer-generated limitations drop entry: `template` is a
    localized `LABELS` string with a `{qualified_id}` placeholder; `panelist`
    and `item_id` are both closed-vocabulary/regex-constrained values
    already validated upstream, but `esc` still runs over the whole
    formatted string per the blanket escaping contract (spec §7)."""
    return esc(template.format(qualified_id=f"{panelist}:{item_id}"))
