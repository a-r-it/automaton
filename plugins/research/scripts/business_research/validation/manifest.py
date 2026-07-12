"""manifest kind (V2 spec §6)."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from business_research.json_io import _DATE_RE
from business_research.models import (
    CAPS_QUANT,
    CAPS_STANDARD,
    CONDITIONAL_ROSTER,
    CORE_ROSTER,
    QUANT_ROLES,
    REQUIRED_TOPICS,
)

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_manifest(doc: Mapping[str, object]) -> list[str]:
    errs: list[str] = []

    if doc.get("schema_version") != "business-research-run-v2":
        errs.append(f"E-manifest-schema-version: expected 'business-research-run-v2', "
                    f"got {doc.get('schema_version')!r}")

    slug = doc.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        errs.append(f"E-manifest-slug: {slug!r} does not match ^[a-z0-9]+(-[a-z0-9]+)*$")

    report_date = doc.get("report_date")
    if not isinstance(report_date, str) or not _DATE_RE.match(report_date):
        errs.append(f"E-manifest-report-date: {report_date!r} is not YYYY-MM-DD")

    language = doc.get("language")
    if language not in ("ru", "en"):
        errs.append(f"E-manifest-language: {language!r} not in {{'ru','en'}}")

    brief = doc.get("brief")
    if not isinstance(brief, str) or not brief:
        errs.append(f"E-manifest-brief: {brief!r} is not a non-empty string")

    roster = doc.get("roster")
    if not isinstance(roster, list):
        errs.append(f"E-manifest-roster: 'roster' missing or not a list, got {roster!r}")
        roster = []

    entries = [e for e in roster if isinstance(e, dict)]
    for i, e in enumerate(roster):
        if not isinstance(e, dict):
            errs.append(f"E-manifest-roster-entry: roster[{i}] is not an object")

    # Raw, not-yet-validated roster-entry ids: any JSON value, including
    # non-string or absent (None). Explicit `Any` (not `Any | None` inferred
    # from bare `.get()`) so `sorted()` below type-checks; unknown/non-str
    # ids are still caught by the 'unknown-id' membership check and reported
    # like any other id — this is the raw shape validation is checking.
    ids: list[Any] = [e.get("id") for e in entries]

    missing_core = [r for r in CORE_ROSTER if r not in ids]
    if missing_core:
        errs.append(f"E-manifest-roster-missing-core: {missing_core}")

    seen, dupes = set(), []
    for rid in ids:
        if rid in seen and rid not in dupes:
            dupes.append(rid)
        seen.add(rid)
    if dupes:
        errs.append(f"E-manifest-roster-duplicate: {dupes}")

    known = set(CORE_ROSTER) | set(CONDITIONAL_ROSTER)
    unknown = sorted({rid for rid in ids if rid not in known})
    if unknown:
        errs.append(f"E-manifest-roster-unknown-id: {unknown} not in closed roster set")

    conditional_ids = [rid for rid in ids if rid in CONDITIONAL_ROSTER]
    if len(conditional_ids) > 3:
        errs.append(f"E-manifest-roster-too-many-conditional: {conditional_ids} exceeds max 3")

    for e in entries:
        rid = e.get("id")

        # kind is fixed by roster membership (spec §6): core ids carry
        # "core", conditional ids "conditional". Only checked for known ids —
        # an unknown id is already flagged above and has no expected kind.
        if rid in CORE_ROSTER and e.get("kind") != "core":
            errs.append(f"E-manifest-roster-kind: {rid} kind must be 'core', "
                        f"got {e.get('kind')!r}")
        elif rid in CONDITIONAL_ROSTER and e.get("kind") != "conditional":
            errs.append(f"E-manifest-roster-kind: {rid} kind must be 'conditional', "
                        f"got {e.get('kind')!r}")

        if rid in CORE_ROSTER and e.get("selection_rule") != "always":
            errs.append(f"E-manifest-roster-selection-rule: {rid} selection_rule must be "
                        f"'always', got {e.get('selection_rule')!r}")
        elif rid in CONDITIONAL_ROSTER:
            sel = e.get("selection_rule")
            if not isinstance(sel, str) or not sel:
                errs.append(f"E-manifest-roster-selection-rule: {rid} selection_rule must be "
                            f"a non-empty string, got {sel!r}")

        if not isinstance(e.get("model"), str) or not e.get("model"):
            errs.append(f"E-manifest-roster-model: {rid} missing non-empty 'model'")

        expected_quant = rid in QUANT_ROLES
        q = e.get("quantitative")
        if not (isinstance(q, bool) and q == expected_quant):
            errs.append(f"E-manifest-roster-quantitative: {rid} quantitative must be "
                        f"{expected_quant}, got {q!r}")

        expected_caps = CAPS_QUANT if rid in QUANT_ROLES else CAPS_STANDARD
        if e.get("caps") != expected_caps:
            errs.append(f"E-manifest-roster-caps: {rid} caps must be {expected_caps}, "
                        f"got {e.get('caps')!r}")

        # A non-str rid can never match a REQUIRED_TOPICS key (all str), so
        # this isinstance guard changes nothing observable — it only lets
        # mypy see what .get(rid, []) already falls back to at runtime.
        expected_topics = REQUIRED_TOPICS.get(rid, []) if isinstance(rid, str) else []
        if e.get("required_topics") != expected_topics:
            errs.append(f"E-manifest-roster-required-topics: {rid} required_topics must be "
                        f"{expected_topics}, got {e.get('required_topics')!r}")

    if isinstance(slug, str):
        expected_build_dir = f".automaton/research/{slug}/"
        if doc.get("build_dir") != expected_build_dir:
            errs.append(f"E-manifest-build-dir: expected {expected_build_dir!r}, "
                        f"got {doc.get('build_dir')!r}")

        expected_report_path = f"sources/research/business/{slug}.html"
        if doc.get("final_report_path") != expected_report_path:
            errs.append(f"E-manifest-final-report-path: expected {expected_report_path!r}, "
                        f"got {doc.get('final_report_path')!r}")

    return errs
