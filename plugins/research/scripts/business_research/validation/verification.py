"""verification kind, survival gate, attempt resolution (V2 spec §5.3, §4)."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NotRequired, TypedDict

from business_research.json_io import _DATE_RE, load_document
from business_research.validation.panel import (
    _D_ID_RE,
    _F_ID_RE,
    _S_ID_RE,
    _dupes,
    validate_panel,
)

# --- verification kind (spec §5.3) --------------------------------------------

_VERIF_TOP_KEYS = {"schema_version", "panelist", "attempt", "verifier_status",
                    "sources", "findings", "data_points", "additional_sources"}
_EVIDENCE_VERDICT_VALUES = ("supports", "contradicts", "unrelated", "unreachable")
_REACHABILITY_VALUES = ("reachable", "blocked", "dead")
_V_ID_RE = re.compile(r"^V[1-9][0-9]*$")


def _derived_verdict(evidence: Sequence[object]) -> str:
    """Spec §5.3 derivation: 'verified' iff >=1 'supports' entry; else
    'contradicted' iff >=1 'contradicts'; else 'unsupported'."""
    verdicts = [e.get("verdict") for e in evidence if isinstance(e, dict)]
    if "supports" in verdicts:
        return "verified"
    if "contradicts" in verdicts:
        return "contradicted"
    return "unsupported"


def _panel_id_set(panel_doc: Mapping[str, object], key: str) -> set[str]:
    items = panel_doc.get(key)
    items = items if isinstance(items, list) else []
    # Walrus so mypy narrows this .get() call (see verif_source_ids below).
    return {raw_id for i in items
            if isinstance(i, dict) and isinstance(raw_id := i.get("id"), str)}


def _check_evidence_entries(errs: list[str], kind_label: str, item_id: object,
                             evidence_entries: list[dict[str, object]],
                             verif_source_ids: set[str]) -> None:
    """Shared per-evidence-entry checks for both findings and data_points:
    source_id resolves within this verification document's own sources,
    verdict is a valid literal, evidence_locator is a non-empty string."""
    for e in evidence_entries:
        esid = e.get("source_id")
        if not isinstance(esid, str) or esid not in verif_source_ids:
            errs.append(f"E-verif-evidence-source-ref: {kind_label} {item_id!r} evidence "
                        f"references unknown source {esid!r}")

        verdict = e.get("verdict")
        if verdict not in _EVIDENCE_VERDICT_VALUES:
            errs.append(f"E-verif-evidence-verdict: {kind_label} {item_id!r} evidence verdict "
                        f"{verdict!r} not in {_EVIDENCE_VERDICT_VALUES}")

        locator = e.get("evidence_locator")
        if not isinstance(locator, str) or not locator:
            errs.append(f"E-verif-evidence-locator: {kind_label} {item_id!r} evidence entry "
                        f"missing non-empty 'evidence_locator'")


def validate_verification(doc: object, panel_doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return ["E-verif-doc-type: verification response must be a single JSON object, "
                f"got {type(doc).__name__}"]
    if not isinstance(panel_doc, dict):
        return ["E-verif-panel-doc-type: panel document must be a single JSON object, "
                f"got {type(panel_doc).__name__}"]

    errs: list[str] = []

    actual_keys = set(doc.keys())
    missing_keys = _VERIF_TOP_KEYS - actual_keys
    extra_keys = actual_keys - _VERIF_TOP_KEYS
    if missing_keys or extra_keys:
        errs.append(f"E-verif-keys: missing {sorted(missing_keys)}, extra {sorted(extra_keys)}")

    if doc.get("schema_version") != "business-verification-v1":
        errs.append(f"E-verif-schema-version: expected 'business-verification-v1', "
                    f"got {doc.get('schema_version')!r}")

    panelist = doc.get("panelist")
    panel_panelist = panel_doc.get("panelist")
    if panelist != panel_panelist:
        errs.append(f"E-verif-panelist-mismatch: verification panelist {panelist!r} "
                    f"does not match panel panelist {panel_panelist!r}")

    attempt = doc.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        errs.append(f"E-verif-attempt: 'attempt' must be a positive integer, got {attempt!r}")

    if doc.get("verifier_status") != "complete":
        errs.append(f"E-verif-status: expected 'complete', got {doc.get('verifier_status')!r}")

    sources = doc.get("sources")
    if not isinstance(sources, list):
        errs.append(f"E-verif-sources: 'sources' missing or not a list, got {sources!r}")
        sources = []
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            errs.append(f"E-verif-source-entry: sources[{i}] is not an object")
    source_entries = [s for s in sources if isinstance(s, dict)]

    findings = doc.get("findings")
    if not isinstance(findings, list):
        errs.append(f"E-verif-findings: 'findings' missing or not a list, got {findings!r}")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errs.append(f"E-verif-finding-entry: findings[{i}] is not an object")
    finding_entries = [f for f in findings if isinstance(f, dict)]

    data_points = doc.get("data_points")
    if not isinstance(data_points, list):
        errs.append(f"E-verif-data-points: 'data_points' missing or not a list, "
                    f"got {data_points!r}")
        data_points = []
    for i, d in enumerate(data_points):
        if not isinstance(d, dict):
            errs.append(f"E-verif-data-point-entry: data_points[{i}] is not an object")
    dp_entries = [d for d in data_points if isinstance(d, dict)]

    additional_sources = doc.get("additional_sources")
    if not isinstance(additional_sources, list):
        errs.append(f"E-verif-additional-sources: 'additional_sources' missing or not a "
                    f"list, got {additional_sources!r}")
        additional_sources = []
    for i, a in enumerate(additional_sources):
        if not isinstance(a, dict):
            errs.append(f"E-verif-additional-source-entry: additional_sources[{i}] is not an object")
    additional_entries = [a for a in additional_sources if isinstance(a, dict)]

    # Walrus binds the `.get()` result to a name so mypy can narrow it (a
    # second bare `s.get("id")` call in the guard, as before, is not
    # narrowed — same value, same check, different call expression). The
    # walrus target leaks to function scope (PEP 572); named distinctly
    # from the loop-local `sid` below to avoid any confusion.
    verif_source_ids = {raw_id for s in source_entries
                         if isinstance(raw_id := s.get("id"), str)}

    # --- sources: id grammar + reachability + duplicates -------------------
    for s in source_entries:
        sid = s.get("id")
        if not isinstance(sid, str) or not _S_ID_RE.match(sid):
            errs.append(f"E-verif-source-id: {sid!r} does not match ^S[1-9][0-9]*$")
        reach = s.get("reachability")
        if reach not in _REACHABILITY_VALUES:
            errs.append(f"E-verif-source-reachability: source {sid!r} reachability {reach!r} "
                        f"not in {_REACHABILITY_VALUES}")
    dup = _dupes([s.get("id") for s in source_entries if isinstance(s.get("id"), str)])
    if dup:
        errs.append(f"E-verif-source-id-duplicate: {dup}")

    # --- panel-side lookups (defensive against a malformed panel doc) ------
    panel_findings = panel_doc.get("findings")
    panel_findings = panel_findings if isinstance(panel_findings, list) else []
    panel_finding_entries = [f for f in panel_findings if isinstance(f, dict)]
    panel_f_ids = {raw_id for f in panel_finding_entries
                    if isinstance(raw_id := f.get("id"), str)}

    panel_finding_source_ids: dict[str, set[str]] = {}
    for f in panel_finding_entries:
        pfid = f.get("id")
        if not isinstance(pfid, str):
            continue
        sids = f.get("source_ids")
        panel_finding_source_ids[pfid] = {s for s in sids if isinstance(s, str)} \
            if isinstance(sids, list) else set()

    panel_d_ids = _panel_id_set(panel_doc, "data_points")
    panel_s_ids = _panel_id_set(panel_doc, "sources")

    # --- coverage equality (spec §5.3, AC1: missing AND extra) -------------
    verif_f_ids = {raw_id for f in finding_entries
                    if isinstance(raw_id := f.get("id"), str)}
    missing = sorted(panel_f_ids - verif_f_ids)
    extra = sorted(verif_f_ids - panel_f_ids)
    if missing:
        errs.append(f"E-verif-coverage-findings-missing: {missing}")
    if extra:
        errs.append(f"E-verif-coverage-findings-extra: {extra}")

    verif_d_ids = {raw_id for d in dp_entries
                    if isinstance(raw_id := d.get("id"), str)}
    missing = sorted(panel_d_ids - verif_d_ids)
    extra = sorted(verif_d_ids - panel_d_ids)
    if missing:
        errs.append(f"E-verif-coverage-data-points-missing: {missing}")
    if extra:
        errs.append(f"E-verif-coverage-data-points-extra: {extra}")

    missing = sorted(panel_s_ids - verif_source_ids)
    extra = sorted(verif_source_ids - panel_s_ids)
    if missing:
        errs.append(f"E-verif-coverage-sources-missing: {missing}")
    if extra:
        errs.append(f"E-verif-coverage-sources-extra: {extra}")

    # --- findings: id grammar, per-source evidence coverage, derivation ----
    for f in finding_entries:
        fid = f.get("id")
        if not isinstance(fid, str) or not _F_ID_RE.match(fid):
            errs.append(f"E-verif-finding-id: {fid!r} does not match ^F[1-9][0-9]*$")

        evidence = f.get("evidence")
        if not isinstance(evidence, list):
            errs.append(f"E-verif-finding-evidence: finding {fid!r} 'evidence' missing or "
                        f"not a list")
            evidence = []
        for i, e in enumerate(evidence):
            if not isinstance(e, dict):
                errs.append(f"E-verif-evidence-entry: finding {fid!r} evidence[{i}] is not an object")
        evidence_entries = [e for e in evidence if isinstance(e, dict)]

        _check_evidence_entries(errs, "finding", fid, evidence_entries, verif_source_ids)

        # Every finding's evidence source_ids must be a superset of that
        # finding's panel-declared source_ids (spec §5.3, AC2).
        if isinstance(fid, str) and fid in panel_finding_source_ids:
            needed = panel_finding_source_ids[fid]
            got = {e.get("source_id") for e in evidence_entries if isinstance(e.get("source_id"), str)}
            uncovered = sorted(needed - got)
            if uncovered:
                errs.append(f"E-verif-evidence-coverage: finding {fid!r} evidence does not "
                            f"cover panel source_ids {uncovered}")

        given_verdict = f.get("verdict")
        derived = _derived_verdict(evidence_entries)
        if given_verdict != derived:
            errs.append(f"E-verif-verdict-derivation: finding {fid!r} verdict "
                        f"{given_verdict!r} does not match derived {derived!r} from evidence")

    dup = _dupes([f.get("id") for f in finding_entries if isinstance(f.get("id"), str)])
    if dup:
        errs.append(f"E-verif-finding-id-duplicate: {dup}")

    # --- data_points: id grammar, derivation (no source coverage rule; a --
    # calculated point may legitimately carry no external source_id) -------
    for d in dp_entries:
        did = d.get("id")
        if not isinstance(did, str) or not _D_ID_RE.match(did):
            errs.append(f"E-verif-data-point-id: {did!r} does not match ^D[1-9][0-9]*$")

        evidence = d.get("evidence")
        if not isinstance(evidence, list):
            errs.append(f"E-verif-data-point-evidence: data point {did!r} 'evidence' "
                        f"missing or not a list")
            evidence = []
        for i, e in enumerate(evidence):
            if not isinstance(e, dict):
                errs.append(f"E-verif-evidence-entry: data point {did!r} evidence[{i}] "
                            f"is not an object")
        evidence_entries = [e for e in evidence if isinstance(e, dict)]

        _check_evidence_entries(errs, "data point", did, evidence_entries, verif_source_ids)

        given_verdict = d.get("verdict")
        derived = _derived_verdict(evidence_entries)
        if given_verdict != derived:
            errs.append(f"E-verif-verdict-derivation: data point {did!r} verdict "
                        f"{given_verdict!r} does not match derived {derived!r} from evidence")

    dup = _dupes([d.get("id") for d in dp_entries if isinstance(d.get("id"), str)])
    if dup:
        errs.append(f"E-verif-data-point-id-duplicate: {dup}")

    # --- additional_sources: the only channel for undeclared evidence ------
    for a in additional_entries:
        aid = a.get("id")
        if not isinstance(aid, str) or not _V_ID_RE.match(aid):
            errs.append(f"E-verif-additional-source-id: {aid!r} does not match ^V[1-9][0-9]*$")

        url = a.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            errs.append(f"E-verif-additional-source-url: additional source {aid!r} url "
                        f"{url!r} must start with https://")

        if not isinstance(a.get("title"), str) or not a.get("title"):
            errs.append(f"E-verif-additional-source-title: additional source {aid!r} "
                        f"missing non-empty title")

        if not isinstance(a.get("publisher"), str) or not a.get("publisher"):
            errs.append(f"E-verif-additional-source-publisher: additional source {aid!r} "
                        f"missing non-empty publisher")

        accessed_at = a.get("accessed_at")
        if not isinstance(accessed_at, str) or not _DATE_RE.match(accessed_at):
            errs.append(f"E-verif-additional-source-date: additional source {aid!r} "
                        f"accessed_at {accessed_at!r} is not YYYY-MM-DD")

        if not isinstance(a.get("usage"), str) or not a.get("usage"):
            errs.append(f"E-verif-additional-source-usage: additional source {aid!r} "
                        f"missing non-empty usage")

        relates_to = a.get("relates_to")
        if not isinstance(relates_to, list):
            errs.append(f"E-verif-additional-source-relates-to: additional source {aid!r} "
                        f"'relates_to' missing or not a list")
            relates_to = []
        for rid in relates_to:
            if not isinstance(rid, str):
                errs.append(f"E-verif-additional-source-relates-to: additional source "
                            f"{aid!r} 'relates_to' entry {rid!r} is not a string")
            elif rid not in panel_f_ids:
                errs.append(f"E-verif-additional-source-relates-to: additional source "
                            f"{aid!r} 'relates_to' references unknown panel finding {rid!r}")

    dup = _dupes([a.get("id") for a in additional_entries if isinstance(a.get("id"), str)])
    if dup:
        errs.append(f"E-verif-additional-source-id-duplicate: {dup}")

    return errs


# --- survival gate (spec §5.3) --------------------------------------------------

def survival_errors(
    verification_doc: object, manifest_entry: object, panel_doc: object
) -> list[str]:
    """Per-panelist survival gate, run after verification. Three rules:
    (1) >=1 verified finding; (2) every manifest required_topics entry
    retains >=1 verified finding carrying that topic (topic lives on the
    *panel* finding, verdict lives on the *verification* finding — joined
    by finding id); (3) quantitative roles retain >=1 verified data point."""
    if not isinstance(verification_doc, dict):
        return ["E-survival-doc-type: verification document must be a single JSON object, "
                f"got {type(verification_doc).__name__}"]
    if not isinstance(manifest_entry, dict):
        return ["E-survival-manifest-entry-type: manifest roster entry must be a single "
                f"JSON object, got {type(manifest_entry).__name__}"]
    if not isinstance(panel_doc, dict):
        return ["E-survival-panel-doc-type: panel document must be a single JSON object, "
                f"got {type(panel_doc).__name__}"]

    errs: list[str] = []

    verif_findings = verification_doc.get("findings")
    verif_findings = verif_findings if isinstance(verif_findings, list) else []
    verified_finding_ids = {f.get("id") for f in verif_findings
                             if isinstance(f, dict) and f.get("verdict") == "verified"
                             and isinstance(f.get("id"), str)}

    if not verified_finding_ids:
        errs.append("E-survival-no-verified-finding: panelist retains zero verified findings")

    panel_findings = panel_doc.get("findings")
    panel_findings = panel_findings if isinstance(panel_findings, list) else []
    topic_by_id = {f.get("id"): f.get("topic") for f in panel_findings if isinstance(f, dict)}

    required_topics = manifest_entry.get("required_topics")
    required_topics = required_topics if isinstance(required_topics, list) else []
    for topic in required_topics:
        if not isinstance(topic, str):
            continue
        if not any(topic_by_id.get(fid) == topic for fid in verified_finding_ids):
            errs.append(f"E-survival-required-topic:{topic}: no verified finding retains "
                        f"required topic {topic!r}")

    if manifest_entry.get("quantitative") is True:
        verif_dps = verification_doc.get("data_points")
        verif_dps = verif_dps if isinstance(verif_dps, list) else []
        has_verified_dp = any(isinstance(d, dict) and d.get("verdict") == "verified"
                               for d in verif_dps)
        if not has_verified_dp:
            errs.append("E-survival-no-verified-datapoint: quantitative role retains zero "
                        "verified data points")

    return errs


# --- attempt resolution (spec §4) -----------------------------------------------

_ATTEMPT_RE_TEMPLATE = r"^{}\.a([1-9][0-9]*)\.json$"
_ATTEMPT_FILENAME_RE = re.compile(r"\.a([1-9][0-9]*)\.json$")


class _Survivor(TypedDict):
    """One `surviving_attempts` result entry — bookkeeping this module
    builds itself (not raw external JSON, so a TypedDict fits here unlike
    the raw-dict validator params elsewhere in this file). `panel` and
    `verification` stay `object`: both are whatever `load_document`
    returned for that attempt, already re-validated by
    `validate_panel`/`validate_verification` by the time they land here,
    but not re-narrowed to a models.py contract. `superseded` is
    NotRequired because it's added after the record is first built."""
    attempt: int
    panel: object
    verification: object
    superseded: NotRequired[list[str]]


def attempt_filename_errors(verification_doc: object, n: int) -> list[str]:
    """Cross-checks a verification document's own `attempt` field against
    the attempt number `n` embedded in the filename it was staged/validated
    as (spec §4: `verification/<id>.a<N>.json` — the two must agree, or a
    verification response copy-pasted from a different attempt could be
    silently accepted under the wrong attempt number). Shared by
    `surviving_attempts` (mismatch is just one more reason an attempt
    doesn't survive, alongside any other per-attempt validation failure)
    and by the verification CLI / the renderer's missing-survivor
    diagnostic, which both want the named error line."""
    attempt = verification_doc.get("attempt") if isinstance(verification_doc, dict) else None
    if attempt != n:
        return [f"E-verif-attempt-filename-mismatch: attempt {attempt!r} does not match "
                f"filename attempt number {n}"]
    return []


def attempt_number_from_filename(path: str | None) -> int | None:
    """Extracts N from a `....a<N>.json` filename (`panel/<id>.a<N>.json` /
    `verification/<id>.a<N>.json`, spec §4). Returns `None` when `path` is
    falsy or its basename doesn't carry the pattern — callers treat that as
    "no attempt number to cross-check" rather than an error, so ad hoc
    paths outside the `a<N>` naming convention (e.g. a bare test fixture
    file) are simply skipped rather than forced to comply."""
    if not path:
        return None
    m = _ATTEMPT_FILENAME_RE.search(Path(path).name)
    return int(m.group(1)) if m else None


def surviving_attempts(
    build_dir: str, manifest: Mapping[str, object]
) -> dict[str, _Survivor | None]:
    """Per roster panelist, the highest attempt number whose panel file
    passes `validate_panel`, whose matching verification file passes
    `validate_verification` against that panel doc, and whose verification
    passes `survival_errors` against the manifest roster entry. Determined
    purely from files on disk under `build_dir` (no extra state).

    Returns `{panelist_id: {"attempt": n, "panel": doc, "verification": doc,
    "superseded": [filenames]}}`; a panelist with no surviving attempt maps
    to `None`. `superseded` filenames are build-dir-relative POSIX paths
    (`panel/<id>.a<N>.json`, `verification/<id>.a<N>.json`) for every
    considered attempt other than the surviving one.
    """
    build_path = Path(build_dir)
    roster = manifest.get("roster") if isinstance(manifest, dict) else None
    roster = roster if isinstance(roster, list) else []

    result: dict[str, _Survivor | None] = {}
    for entry in roster:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("id")
        if not isinstance(pid, str):
            continue

        pattern = re.compile(_ATTEMPT_RE_TEMPLATE.format(re.escape(pid)))
        attempt_nums: list[int] = []
        for pf in sorted(build_path.glob(f"panel/{pid}.a*.json")):
            m = pattern.match(pf.name)
            if m:
                attempt_nums.append(int(m.group(1)))
        attempt_nums.sort(reverse=True)

        survivor: _Survivor | None = None
        considered: list[str] = []
        for n in attempt_nums:
            panel_rel = f"panel/{pid}.a{n}.json"
            verif_rel = f"verification/{pid}.a{n}.json"
            verif_path = build_path / verif_rel
            considered.append(panel_rel)
            if verif_path.exists():
                considered.append(verif_rel)

            if survivor is not None:
                continue  # highest-passing attempt already found; keep collecting filenames

            panel_path = build_path / panel_rel
            panel_doc, panel_load_errs = load_document(panel_path)
            if panel_doc is None or panel_load_errs:
                continue
            if validate_panel(panel_doc, manifest) != []:
                continue
            if not verif_path.exists():
                continue
            verif_doc, verif_load_errs = load_document(verif_path)
            if verif_doc is None or verif_load_errs:
                continue
            if validate_verification(verif_doc, panel_doc) != []:
                continue
            # A verification response staged under the wrong attempt's
            # filename (e.g. an a2 response copy-pasted into a1.json,
            # 'attempt' field left at 2) invalidates this attempt the same
            # way any other check failure does: skip to the next-lower
            # attempt number. `_diagnose_missing_survivor` (renderer) names
            # this specific cause when no attempt survives at all.
            if attempt_filename_errors(verif_doc, n):
                continue
            if survival_errors(verif_doc, entry, panel_doc) != []:
                continue
            survivor = {"attempt": n, "panel": panel_doc, "verification": verif_doc}

        if survivor is None:
            result[pid] = None
            continue

        winning = {f"panel/{pid}.a{survivor['attempt']}.json",
                   f"verification/{pid}.a{survivor['attempt']}.json"}
        survivor["superseded"] = sorted(f for f in set(considered) if f not in winning)
        result[pid] = survivor

    return result
