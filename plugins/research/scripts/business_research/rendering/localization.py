"""Localized labels and HTML/formatting primitives (V2 spec §8)."""

from __future__ import annotations

import html as _html
from collections.abc import Mapping
from typing import TypedDict


class Labels(TypedDict):
    """Exact shape of one language's entry in `LABELS`. mypy enforces that
    both the "ru" and "en" tables satisfy this ONE TypedDict — that sync
    check across languages is the point of typing this table at all. Moves
    unchanged to `localization.py` in Task 10."""

    verdict_decision: dict[str, str]
    report_date: str
    slug: str
    executive_summary: str
    methodology: str
    kpi_strip: str
    risks: str
    recommendations: str
    sources: str
    limitations: str
    disagreements: str
    confidence: dict[str, str]
    severity: dict[str, str]
    found_by_verifier: str
    methodology_pipeline: str
    methodology_col_id: str
    methodology_col_model: str
    methodology_col_selection_rule: str
    methodology_count_sources: str
    methodology_count_findings: str
    methodology_count_data_points: str
    methodology_verified_findings: str  # format template: {verified}, {total}
    methodology_verified_data_points: str  # format template: {verified}, {total}
    reachability: dict[str, str]
    limitations_verification_drops: str
    dropped_finding_unsupported: str  # format template: {qualified_id}
    dropped_finding_contradicted: str  # format template: {qualified_id}
    dropped_finding_disputed: str  # format template: {qualified_id}
    dropped_data_point_unsupported: str  # format template: {qualified_id}
    dropped_data_point_contradicted: str  # format template: {qualified_id}
    dropped_data_point_disputed: str  # format template: {qualified_id}
    dropped_source_blocked: str  # format template: {qualified_id}
    dropped_source_dead: str  # format template: {qualified_id}


LABELS: dict[str, Labels] = {
    "ru": {
        "verdict_decision": {
            "go": "Идти",
            "no-go": "Не идти",
            "conditional-go": "Идти с оговорками",
            "insufficient-evidence": "Недостаточно данных",
        },
        "report_date": "Дата отчёта",
        "slug": "Идентификатор запуска",
        "executive_summary": "Краткое резюме",
        "methodology": "Методология",
        "kpi_strip": "Ключевые показатели",
        "risks": "Риски",
        "recommendations": "Рекомендации",
        "sources": "Источники",
        "limitations": "Ограничения",
        "disagreements": "Разногласия",
        "confidence": {
            "high": "высокая уверенность",
            "medium": "средняя уверенность",
            "low": "низкая уверенность",
        },
        "severity": {"high": "высокая", "medium": "средняя", "low": "низкая"},
        "found_by_verifier": "источник найден верификатором",
        "methodology_pipeline": (
            "Конвейер: постановка задачи → исследование агентами → "
            "независимая верификация → синтез → рендеринг."
        ),
        "methodology_col_id": "Роль",
        "methodology_col_model": "Модель",
        "methodology_col_selection_rule": "Правило отбора",
        "methodology_count_sources": "Источников собрано агентами",
        "methodology_count_findings": "Находок собрано агентами",
        "methodology_count_data_points": "Показателей собрано агентами",
        "methodology_verified_findings": (
            "Находок подтверждено верификацией: {verified} из {total}"
        ),
        "methodology_verified_data_points": (
            "Показателей подтверждено верификацией: {verified} из {total}"
        ),
        "reachability": {
            "reachable": "источник доступен",
            "blocked": "источник заблокирован",
            "dead": "источник недоступен",
        },
        "limitations_verification_drops": "Исключено по результатам верификации",
        "dropped_finding_unsupported": (
            "{qualified_id}: находка не подтверждена верификацией"
        ),
        "dropped_finding_contradicted": (
            "{qualified_id}: находка противоречит источникам по данным верификации"
        ),
        "dropped_finding_disputed": (
            "{qualified_id}: находка оспорена — верификация нашла как подтверждающие, "
            "так и противоречащие источники"
        ),
        "dropped_data_point_unsupported": (
            "{qualified_id}: показатель не подтверждён верификацией"
        ),
        "dropped_data_point_contradicted": (
            "{qualified_id}: показатель противоречит источникам по данным верификации"
        ),
        "dropped_data_point_disputed": (
            "{qualified_id}: показатель оспорен — верификация нашла как подтверждающие, "
            "так и противоречащие источники"
        ),
        "dropped_source_blocked": (
            "{qualified_id}: источник был заблокирован при верификации"
        ),
        "dropped_source_dead": (
            "{qualified_id}: источник оказался недоступен при верификации"
        ),
    },
    "en": {
        "verdict_decision": {
            "go": "Go",
            "no-go": "No-go",
            "conditional-go": "Conditional go",
            "insufficient-evidence": "Insufficient evidence",
        },
        "report_date": "Report date",
        "slug": "Run slug",
        "executive_summary": "Executive summary",
        "methodology": "Methodology",
        "kpi_strip": "Key metrics",
        "risks": "Risks",
        "recommendations": "Recommendations",
        "sources": "Sources",
        "limitations": "Limitations",
        "disagreements": "Disagreements",
        "confidence": {
            "high": "high confidence",
            "medium": "medium confidence",
            "low": "low confidence",
        },
        "severity": {"high": "high", "medium": "medium", "low": "low"},
        "found_by_verifier": "source found by verifier",
        "methodology_pipeline": (
            "Pipeline: scoping → agent research → independent "
            "verification → synthesis → render."
        ),
        "methodology_col_id": "Role",
        "methodology_col_model": "Model",
        "methodology_col_selection_rule": "Selection rule",
        "methodology_count_sources": "Sources collected by the agents",
        "methodology_count_findings": "Findings collected by the agents",
        "methodology_count_data_points": "Data points collected by the agents",
        "methodology_verified_findings": "Findings verified: {verified} of {total}",
        "methodology_verified_data_points": "Data points verified: {verified} of {total}",
        "reachability": {
            "reachable": "source reachable",
            "blocked": "source blocked",
            "dead": "source dead",
        },
        "limitations_verification_drops": "Dropped by verification",
        "dropped_finding_unsupported": "{qualified_id}: finding not supported by verification",
        "dropped_finding_contradicted": (
            "{qualified_id}: finding contradicted by verification"
        ),
        "dropped_finding_disputed": (
            "{qualified_id}: finding disputed — verification found both supporting and "
            "contradicting evidence"
        ),
        "dropped_data_point_unsupported": (
            "{qualified_id}: data point not supported by verification"
        ),
        "dropped_data_point_contradicted": (
            "{qualified_id}: data point contradicted by verification"
        ),
        "dropped_data_point_disputed": (
            "{qualified_id}: data point disputed — verification found both supporting and "
            "contradicting evidence"
        ),
        "dropped_source_blocked": "{qualified_id}: source was blocked during verification",
        "dropped_source_dead": "{qualified_id}: source was dead during verification",
    },
}


def esc(value: object) -> str:
    """HTML-escapes any LLM- or web-derived value for both text and
    attribute contexts (`quote=True` escapes quotes too, so the result is
    always attribute-safe as well as text-safe)."""
    return _html.escape(str(value), quote=True)


def safe_url(url: object) -> str | None:
    """Returns `url` unchanged iff its scheme is `https` (case-insensitive);
    otherwise None, meaning: render as escaped text, never as a link.
    `javascript:`, `data:`, plain `http:`, and non-string values all resolve
    to None."""
    if not isinstance(url, str):
        return None
    return url if url.lower().startswith("https://") else None


def fmt_num(value: float | int, lang: str) -> str:
    """Formats a pre-validated numeric value (finite, <=4 decimal places, no
    exponent notation — the validator already rejects anything else) for
    display: `ru` uses a decimal comma and U+202F thin-space thousands
    grouping; `en` uses a decimal point and comma thousands grouping. The
    canonical value itself is only ever kept in the provenance block."""
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    text = f"{magnitude:.4f}".rstrip("0").rstrip(".")
    int_str, _, frac_str = text.partition(".")
    grouped_int = f"{int(int_str):,}"
    if lang == "ru":
        grouped_int = grouped_int.replace(",", " ")
        decimal_sep = ","
    else:
        decimal_sep = "."
    body = f"{grouped_int}{decimal_sep}{frac_str}" if frac_str else grouped_int
    return f"{sign}{body}"


def _lang(manifest: Mapping[str, object]) -> str:
    """Resolves the report language for `LABELS` lookups (spec §6): the
    manifest's `language` is validated to a closed `ru|en` set, but this
    stays defensive against a future looser vocabulary — an unrecognized
    value falls back to `en` labels while narrative text is left exactly as
    the synthesizer wrote it. Takes `Mapping[str, object]` (a raw validated
    document, per the validator-side convention) rather than
    `models.ManifestDoc` — every caller reaches this through `run.manifest`
    across all five rendering modules, so a `TypedDict`-shaped param here
    would force every one of those call sites (several of them still bare
    `run` params, Task 16-scoped one module at a time) to already carry the
    stronger contract; `Mapping[str, object]` is satisfied by both a bare
    dict and `ManifestDoc` (a valid `Mapping[str, object]` subtype) alike."""
    language = manifest["language"]
    return language if isinstance(language, str) and language in LABELS else "en"


def _wrap_section(section_id: str, heading: str, inner_html: str) -> str:
    """Common `<section><details open>` shell for every top-level report
    section (spec §8, §11: zero JS, `<details open>` for collapsibility —
    emitted open so print/quick-reading works by default). `heading` is a
    plain label string, escaped here; `inner_html` is caller-assembled
    markup — every call site below builds it exclusively from `esc`/
    `safe_url`-passed fragments, so it is trusted verbatim at this point."""
    return (
        f'<section id="{esc(section_id)}" class="report-section">'
        f"<details open><summary>{esc(heading)}</summary>"
        f'<div class="section-body">{inner_html}</div>'
        "</details></section>"
    )
