"""synthesis kind (V2 spec §5.4)."""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from business_research.json_io import load_document
from business_research.validation.agent import _CONFIDENCE_VALUES, _dupes, has_numeric_token
from business_research.validation.manifest import validate_manifest
from business_research.validation.verification import surviving_attempts

# --- synthesis kind (spec §5.4) ------------------------------------------------

_SYNTH_TOP_KEYS = {"schema_version", "slug", "title", "verdict", "executive_summary",
                    "sections", "risks", "recommendations", "limitations"}
_SECTION_KEYS = {"agent", "narrative", "disagreements"}
_VERDICT_KEYS = {"decision", "statement", "confidence", "refs"}
_VERDICT_DECISIONS = ("go", "no-go", "conditional-go", "insufficient-evidence")
# _CONFIDENCE_VALUES lives in business_research.validation.agent (imported
# above) — shared with the agent kind's finding.confidence check (spec §5.1).
_SEVERITY_VALUES = ("high", "medium", "low")
_REF_RE = re.compile(r"^([^:]+):(F|D)([1-9][0-9]*)$")

# {pid: {"F": {id: verdict}, "D": {id: verdict}}}. "F"/"D" are plain str
# keys (looked up dynamically via a regex-derived `kind` variable in
# _check_ref, not TypedDict literals), so this is a regular nested dict
# rather than a TypedDict.
type _SurvivorLookup = dict[str, dict[str, dict[str, object]]]


def _build_survivor_lookup(survivors: Mapping[str, Mapping[str, object] | None]
                            ) -> _SurvivorLookup:
    """{pid: {"F": {id: verdict}, "D": {id: verdict}}}, one entry per
    surviving agent. Verdicts come from the surviving attempt's
    verification document; `surviving_attempts` already proved that
    document's finding/data-point ids equal the agent document's 1:1 (the
    coverage rule inside `validate_verification`), so id *existence* is
    fully answered by the verification document alone — no need to
    cross-check the agent document's ids again here."""
    lookup: _SurvivorLookup = {}
    for pid, survivor in survivors.items():
        if survivor is None:
            continue
        verif_doc = survivor.get("verification")
        verif_doc = verif_doc if isinstance(verif_doc, dict) else {}
        findings = verif_doc.get("findings")
        findings = findings if isinstance(findings, list) else []
        dps = verif_doc.get("data_points")
        dps = dps if isinstance(dps, list) else []
        # Walrus so mypy narrows these .get("id") calls (same limitation as
        # business_research.validation.verification's verif_source_ids: a
        # second .get() call on the same expression doesn't narrow).
        f_verdicts = {raw_id: f.get("verdict") for f in findings
                      if isinstance(f, dict) and isinstance(raw_id := f.get("id"), str)}
        d_verdicts = {raw_id: d.get("verdict") for d in dps
                      if isinstance(d, dict) and isinstance(raw_id := d.get("id"), str)}
        lookup[pid] = {"F": f_verdicts, "D": d_verdicts}
    return lookup


def _check_ref(errs: list[str], context: str, ref: object,
               survivor_lookup: _SurvivorLookup, *, allow_disputed: bool = False) -> bool:
    """Validates one qualified ref (`<roster-id>:F<n>` / `<roster-id>:D<n>`)
    against the surviving-attempt lookup, appending a named error for any
    failure. Returns True iff the ref is a *valid* ':D' ref — the only
    signal the numeric-token rule cares about (a valid ':F' ref, or any
    invalid ref, both count as "no D-ref backing").

    `allow_disputed` (design §6, "disputed findings surface, not vanish"):
    when True, a `disputed`-verdict id also resolves — used ONLY for the
    `disagreements[]` ref-walk. A `disputed` finding fails survival (not
    citable as verified evidence elsewhere), but it carries genuine
    conflict signal that belongs in disagreements. `contradicted` and
    `unsupported` verdicts are never allowed, in `disagreements` or
    anywhere else."""
    if not isinstance(ref, str):
        errs.append(f"E-synth-ref-unknown: {context} ref {ref!r} is not a string")
        return False
    m = _REF_RE.match(ref)
    if not m:
        errs.append(f"E-synth-ref-unknown: {context} ref {ref!r} does not match "
                    f"'^<roster-id>:(F|D)[1-9][0-9]*$'")
        return False
    pid, kind, num = m.group(1), m.group(2), m.group(3)
    ids = survivor_lookup.get(pid)
    if ids is None:
        errs.append(f"E-synth-ref-unknown: {context} ref {ref!r} — {pid!r} is not a "
                    f"surviving roster agent")
        return False
    item_id = f"{kind}{num}"
    verdict = ids[kind].get(item_id)
    if verdict is None:
        errs.append(f"E-synth-ref-unknown: {context} ref {ref!r} — {item_id!r} not found for "
                    f"agent {pid!r}")
        return False
    if verdict != "verified" and not (allow_disputed and verdict == "disputed"):
        errs.append(f"E-synth-ref-unverified: {context} ref {ref!r} — {item_id!r} verdict "
                    f"{verdict!r} is not 'verified'")
        return False
    return kind == "D"


def _check_ref_items(errs: list[str], label: str, items: object, allowed_keys: set[str],
                      text_key: str, *, refs_required: bool, survivor_lookup: _SurvivorLookup,
                      literal_field: tuple[str, tuple[str, ...]] | None = None,
                      allow_disputed: bool = False) -> None:
    """Shared per-item walk for every synthesis evidentiary list (spec §5.4):
    shape (exact keys), ref grammar/resolution, the mandatory-ref rule, and
    the numeric-token-requires-a-D-ref rule. `literal_field` is an optional
    (field_name, allowed_values) pair for risks' 'severity'. `allow_disputed`
    is passed through to `_check_ref` unchanged — True ONLY for the
    `sections[].disagreements` call site (design §6)."""
    if not isinstance(items, list):
        errs.append(f"E-synth-{label}-list: {label!r} missing or not a list, got {items!r}")
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errs.append(f"E-synth-{label}-entry: {label}[{i}] is not an object")
            continue

        actual = set(item.keys())
        if actual != allowed_keys:
            errs.append(f"E-synth-{label}-keys: {label}[{i}] keys {sorted(actual)} != "
                        f"{sorted(allowed_keys)}")

        text = item.get(text_key)
        if not isinstance(text, str) or not text:
            errs.append(f"E-synth-{label}-{text_key}: {label}[{i}] missing non-empty {text_key!r}")
            text = ""

        if literal_field is not None:
            field_name, allowed_values = literal_field
            value = item.get(field_name)
            if value not in allowed_values:
                errs.append(f"E-synth-{label}-{field_name}: {label}[{i}] {field_name} "
                            f"{value!r} not in {allowed_values}")

        refs = item.get("refs")
        if not isinstance(refs, list):
            errs.append(f"E-synth-{label}-refs-type: {label}[{i}] 'refs' missing or not a list")
            refs = []
        if refs_required and not refs:
            errs.append(f"E-synth-missing-ref: {label}[{i}] requires >=1 ref")

        # List comprehension, not any(generator): _check_ref's error-appending
        # side effect must run for every ref, not stop at the first D-ref hit.
        dref_flags = [_check_ref(errs, f"{label}[{i}]", ref, survivor_lookup,
                                  allow_disputed=allow_disputed) for ref in refs]

        if has_numeric_token(text) and not any(dref_flags):
            errs.append(f"E-synth-numeric-no-dref: {label}[{i}] {text_key} carries a numeric "
                        f"token but refs contain no ':D' reference")


def validate_synthesis(doc: object, build_dir: str) -> list[str]:
    if not isinstance(doc, dict):
        return ["E-synth-doc-type: synthesis response must be a single JSON object, "
                f"got {type(doc).__name__}"]
    if not isinstance(build_dir, str) or not build_dir:
        return ["E-synth-build-dir: build_dir must be a non-empty string"]

    manifest_doc, load_errs = load_document(Path(build_dir) / "manifest.json")
    if manifest_doc is None:
        return load_errs
    manifest_errs = load_errs + validate_manifest(manifest_doc)
    if manifest_errs:
        return manifest_errs

    errs: list[str] = []

    actual_keys = set(doc.keys())
    missing_keys = _SYNTH_TOP_KEYS - actual_keys
    extra_keys = actual_keys - _SYNTH_TOP_KEYS
    if missing_keys or extra_keys:
        errs.append(f"E-synth-keys: missing {sorted(missing_keys)}, extra {sorted(extra_keys)}")

    if doc.get("schema_version") != "business-synthesis-v1":
        errs.append(f"E-synth-schema-version: expected 'business-synthesis-v1', "
                    f"got {doc.get('schema_version')!r}")

    slug = doc.get("slug")
    manifest_slug = manifest_doc.get("slug")
    if not isinstance(slug, str) or slug != manifest_slug:
        errs.append(f"E-synth-slug: {slug!r} does not match manifest slug {manifest_slug!r}")

    title = doc.get("title")
    if not isinstance(title, str) or not title:
        errs.append(f"E-synth-title: 'title' missing or not a non-empty string, got {title!r}")

    survivors = surviving_attempts(build_dir, manifest_doc)
    survivor_lookup = _build_survivor_lookup(survivors)
    survivor_ids = {pid for pid, s in survivors.items() if s is not None}

    # A roster agent with no surviving attempt is a build-dir defect —
    # aligned with the renderer's load_run, which refuses such a build dir
    # (spec §5.4). Reachable only via hand-run CLI: the SKILL's survival
    # gate aborts the run before synthesis ever sees this state.
    for pid in sorted(pid for pid, s in survivors.items() if s is None):
        errs.append(f"E-synth-missing-survivor: {pid}: no surviving attempt in build dir")

    # --- verdict -------------------------------------------------------------
    verdict = doc.get("verdict")
    if not isinstance(verdict, dict):
        errs.append(f"E-synth-verdict-type: 'verdict' missing or not an object, got {verdict!r}")
        verdict = {}
    else:
        actual = set(verdict.keys())
        if actual != _VERDICT_KEYS:
            errs.append(f"E-synth-verdict-keys: verdict keys {sorted(actual)} != "
                        f"{sorted(_VERDICT_KEYS)}")

    decision = verdict.get("decision")
    if decision not in _VERDICT_DECISIONS:
        errs.append(f"E-synth-verdict-decision: {decision!r} not in {_VERDICT_DECISIONS}")

    statement = verdict.get("statement")
    if not isinstance(statement, str) or not statement:
        errs.append("E-synth-verdict-statement: 'statement' missing or not a non-empty string")
        statement = ""

    confidence = verdict.get("confidence")
    if confidence not in _CONFIDENCE_VALUES:
        errs.append(f"E-synth-verdict-confidence: {confidence!r} not in {_CONFIDENCE_VALUES}")

    verdict_refs = verdict.get("refs")
    if not isinstance(verdict_refs, list):
        errs.append("E-synth-verdict-refs-type: verdict 'refs' missing or not a list")
        verdict_refs = []
    if not verdict_refs:
        errs.append("E-synth-missing-ref: verdict requires >=1 ref")

    # List comprehension, not any(generator): _check_ref's error-appending
    # side effect must run for every ref, not stop at the first D-ref hit.
    dref_flags = [_check_ref(errs, "verdict", ref, survivor_lookup) for ref in verdict_refs]

    if has_numeric_token(statement) and not any(dref_flags):
        errs.append("E-synth-numeric-no-dref: verdict.statement carries a numeric "
                    "token but refs contain no ':D' reference")

    # --- flat evidentiary lists ------------------------------------------------
    item_table = [
        ("executive_summary", doc.get("executive_summary"), {"text", "refs"}, "text", True, None),
        ("risks", doc.get("risks"), {"risk", "severity", "refs"}, "risk", True,
         ("severity", _SEVERITY_VALUES)),
        ("recommendations", doc.get("recommendations"), {"recommendation", "refs"},
         "recommendation", True, None),
        ("limitations", doc.get("limitations"), {"text", "refs"}, "text", False, None),
    ]
    for label, items, allowed_keys, text_key, refs_required, literal_field in item_table:
        _check_ref_items(errs, label, items, allowed_keys, text_key,
                          refs_required=refs_required, survivor_lookup=survivor_lookup,
                          literal_field=literal_field)

    # --- sections: one per surviving roster entry, no heading, ref-checked ----
    sections = doc.get("sections")
    if not isinstance(sections, list):
        errs.append(f"E-synth-sections-list: 'sections' missing or not a list, got {sections!r}")
        sections = []

    section_agents = []
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            errs.append(f"E-synth-section-entry: sections[{i}] is not an object")
            continue

        actual = set(section.keys())
        if actual != _SECTION_KEYS:
            errs.append(f"E-synth-section-keys: sections[{i}] keys {sorted(actual)} != "
                        f"{sorted(_SECTION_KEYS)}")

        agent = section.get("agent")
        if not isinstance(agent, str) or not agent:
            errs.append(f"E-synth-section-agent: sections[{i}] missing non-empty 'agent'")
        else:
            section_agents.append(agent)

        _check_ref_items(errs, f"sections[{i}].narrative", section.get("narrative"),
                          {"text", "refs"}, "text", refs_required=True,
                          survivor_lookup=survivor_lookup)
        _check_ref_items(errs, f"sections[{i}].disagreements", section.get("disagreements"),
                          {"text", "refs"}, "text", refs_required=True,
                          survivor_lookup=survivor_lookup, allow_disputed=True)

    dup = _dupes(section_agents)
    if dup:
        errs.append(f"E-synth-sections-duplicate: {dup}")

    missing = sorted(survivor_ids - set(section_agents))
    if missing:
        errs.append(f"E-synth-sections-missing: {missing}")

    extra = sorted(set(section_agents) - survivor_ids)
    if extra:
        errs.append(f"E-synth-sections-extra: {extra}")

    return errs
