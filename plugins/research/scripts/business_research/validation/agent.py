"""agent kind (V2 spec §5.1) — findings, data points, formulas."""
from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence

from business_research.json_io import _DATE_RE

# --- Numeric-token heuristic (spec §5.1) -------------------------------------

_IDENT = re.compile(r"\b(?=\w*[A-Za-z])(?=\w*\d)\w+\b")  # B2B, Q2, 5G — mixed alnum ids
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_MONEY = re.compile(r"[%$€₽£]")


def has_numeric_token(text: str) -> bool:
    """Backstop heuristic (spec §5.1): digits excluding standalone 4-digit
    years and alphanumeric identifiers (B2B, Q2), plus money/% symbols.
    Prose quantities ("half", "double the market") are deliberately NOT
    caught here — cross-checking prose quantities against sources is the
    verifier's job (§5.3), not this mechanical validator's."""
    stripped = _YEAR.sub("", _IDENT.sub("", text))
    return bool(re.search(r"\d", stripped)) or bool(_MONEY.search(text))


# --- Formula parsing (calculated data points, spec §5.1) ---------------------

_FORMULA_TOKEN = re.compile(r"\s*(D[1-9][0-9]*|\d+(?:\.\d+)?|[()+\-*/])\s*")


_FORMULA_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


def formula_ids(formula: str) -> tuple[set[str] | None, str | None]:
    """Parses a calculated data point's formula against a real arithmetic
    grammar (spec §5.1):

        expr   := term (('+' | '-') term)*
        term   := factor (('*' | '/') factor)*
        factor := NUMBER | D-id | '(' expr ')'

    Returns `(id-set, None)` iff the formula tokenizes cleanly *and* the
    full token stream matches `expr` with nothing left over. Returns
    `(None, error)` on the first violation: an unrecognized character
    during tokenization, an empty formula, two factors with no operator
    between them (`"D1 D2"`), a trailing operator (`"D1 +"`), or empty
    parentheses (`"()"`). Does not validate that the referenced ids exist
    elsewhere in the document, or check for cycles — those cross-checks
    belong to the agent-kind validator, which has the full document to
    check against.

    Implemented as three mutually-recursive position-threading helpers
    (`_factor`/`_term`/`_expr`, each `token index -> next index | None`)
    rather than a stateful cursor object, so parsing stays a set of pure
    functions over the token list; only the `ids` accumulator is a shared
    side effect, and only `_factor` ever writes to it.
    """
    tokens: list[str] = []
    pos = 0
    while pos < len(formula):
        m = _FORMULA_TOKEN.match(formula, pos)
        if not m:
            return None, f"E-formula-token: unexpected char at {pos!r} in {formula!r}"
        tokens.append(m.group(1))
        pos = m.end()
    if not tokens:
        return None, f"E-formula-empty: formula {formula!r} is empty"

    ids: set[str] = set()

    def _factor(i: int) -> int | None:
        if i >= len(tokens):
            return None
        tok = tokens[i]
        if tok == "(":
            j = _expr(i + 1)
            if j is None or j >= len(tokens) or tokens[j] != ")":
                return None
            return j + 1
        if tok.startswith("D"):
            ids.add(tok)
            return i + 1
        if _FORMULA_NUMBER.match(tok):
            return i + 1
        return None

    def _term(i: int) -> int | None:
        j = _factor(i)
        while j is not None and j < len(tokens) and tokens[j] in ("*", "/"):
            j = _factor(j + 1)
        return j

    def _expr(i: int) -> int | None:
        j = _term(i)
        while j is not None and j < len(tokens) and tokens[j] in ("+", "-"):
            j = _term(j + 1)
        return j

    end = _expr(0)
    if end is None or end != len(tokens):
        return None, (f"E-formula-grammar: {formula!r} does not match "
                       f"expr := term (('+'|'-') term)*")

    return ids, None


# --- agent kind (spec §5.1) ---------------------------------------------------

_AGENT_TOP_KEYS = {"schema_version", "agent", "status", "summary", "findings",
                    "data_points", "sources", "limitations", "disconfirming_evidence",
                    "scope_digest"}
_DISCONFIRMING_NONE_KEYS = {"status", "searched"}
# _F_ID_RE / _D_ID_RE / _S_ID_RE: shared with the verification kind's own id
# grammar checks (business_research.validation.verification, spec §5.3) — the
# same F<n>/D<n>/S<n> grammar applies to both kinds' ids, imported back from
# here rather than duplicated (sanctioned DAG: verification -> agent).
_F_ID_RE = re.compile(r"^F[1-9][0-9]*$")
_D_ID_RE = re.compile(r"^D[1-9][0-9]*$")
_S_ID_RE = re.compile(r"^S[1-9][0-9]*$")
_PERIOD_RE = re.compile(r"^(\d{4}(-Q[1-4]|-\d{2})?|not_applicable)$")
_GEO_RE = re.compile(r"^[A-Z]{2}$")
_DP_KINDS = ("observed", "estimated", "calculated")
# Shared with the synthesis kind's verdict.confidence check
# (business_research.validation.synthesis, spec §5.4) — one closed vocabulary
# for "confidence" across the whole schema family (sanctioned DAG: synthesis
# -> agent).
_CONFIDENCE_VALUES = ("high", "medium", "low")


def _dupes[T](ids: Sequence[T]) -> list[T]:
    """First-seen-repeat duplicates from an id list, order preserved. Generic
    over the id type: every caller passes an already-`isinstance`-filtered
    `list[str]`, except a few verification.py comprehensions where mypy
    can't correlate two separate `.get()` calls and infers `list[Any |
    None]` — this stays generic rather than forcing `str` so those callers
    don't need an unrelated walrus-narrowing rewrite just to satisfy this
    helper's signature."""
    seen: set[T] = set()
    dup: list[T] = []
    for i in ids:
        if i in seen and i not in dup:
            dup.append(i)
        seen.add(i)
    return dup


def _find_roster_entry(manifest: object, agent_id: str) -> dict[str, object] | None:
    roster = manifest.get("roster") if isinstance(manifest, dict) else None
    if not isinstance(roster, list):
        return None
    for e in roster:
        if isinstance(e, dict) and e.get("id") == agent_id:
            return e
    return None


def _find_formula_cycle(graph: dict[object, list[str]]) -> list[object] | None:
    """Iterative DFS (3-color) over {dp_id: [input_ids]} restricted to
    calculated data points. Returns the first cyclic path found, else None.
    Keys are `object`, not `str`: the calling loop's data-point id (`did`)
    isn't `isinstance`-narrowed at the call site (a malformed non-str id is
    already reported elsewhere as E-research-data-point-id and this graph is
    still built the same way for it, unchanged from pre-strict behavior)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    for start in graph:
        if color[start] != WHITE:
            continue
        color[start] = GRAY
        path = [start]
        stack = [(start, iter(graph.get(start, [])))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if nxt not in graph:
                    continue
                if color.get(nxt) == GRAY:
                    return path + [nxt]
                if color.get(nxt) == WHITE:
                    color[nxt] = GRAY
                    path.append(nxt)
                    stack.append((nxt, iter(graph.get(nxt, []))))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
                path.pop()
    return None


def validate_agent(doc: object, manifest: Mapping[str, object],
                    expected_agent: str | None = None) -> list[str]:
    if not isinstance(doc, dict):
        return ["E-research-doc-type: agent response must be a single JSON object, "
                f"got {type(doc).__name__}"]

    errs: list[str] = []

    agent_id = doc.get("agent")
    entry = _find_roster_entry(manifest, agent_id) if isinstance(agent_id, str) else None
    if entry is None:
        errs.append(f"E-research-unknown-agent: {agent_id!r} not found in manifest roster")

    # --- identity: staged file basename must match the doc's declared agent
    # (spec: closes the hole where a structurally-valid doc is written to the
    # wrong agent's path). expected_agent is None for ad hoc/bare invocations
    # (no known filename to bind against) — the check is then skipped.
    if expected_agent is not None and agent_id != expected_agent:
        errs.append(f"E-research-identity: doc agent {agent_id!r} != expected {expected_agent!r}")

    actual_keys = set(doc.keys())
    missing_keys = _AGENT_TOP_KEYS - actual_keys
    extra_keys = actual_keys - _AGENT_TOP_KEYS
    if missing_keys or extra_keys:
        errs.append(f"E-research-keys: missing {sorted(missing_keys)}, extra {sorted(extra_keys)}")

    if doc.get("schema_version") != "business-agent-v2":
        errs.append(f"E-research-schema-version: expected 'business-agent-v2', "
                    f"got {doc.get('schema_version')!r}")

    if doc.get("status") != "complete":
        errs.append(f"E-research-status: expected 'complete', got {doc.get('status')!r}")

    if doc.get("scope_digest") != manifest.get("scope_digest"):
        errs.append(f"E-research-scope-digest: agent scope_digest {doc.get('scope_digest')!r} "
                    f"does not match manifest scope_digest {manifest.get('scope_digest')!r}")

    findings = doc.get("findings")
    if not isinstance(findings, list):
        errs.append(f"E-research-findings: 'findings' missing or not a list, got {findings!r}")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errs.append(f"E-research-finding-entry: findings[{i}] is not an object")
    finding_entries = [f for f in findings if isinstance(f, dict)]

    data_points = doc.get("data_points")
    if not isinstance(data_points, list):
        errs.append(f"E-research-data-points: 'data_points' missing or not a list, "
                    f"got {data_points!r}")
        data_points = []
    for i, d in enumerate(data_points):
        if not isinstance(d, dict):
            errs.append(f"E-research-data-point-entry: data_points[{i}] is not an object")
    dp_entries = [d for d in data_points if isinstance(d, dict)]

    sources = doc.get("sources")
    if not isinstance(sources, list):
        errs.append(f"E-research-sources: 'sources' missing or not a list, got {sources!r}")
        sources = []
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            errs.append(f"E-research-source-entry: sources[{i}] is not an object")
    source_entries = [s for s in sources if isinstance(s, dict)]

    # --- ID grammar + uniqueness -----------------------------------------
    f_ids = [f.get("id") for f in finding_entries]
    for fid in f_ids:
        if not isinstance(fid, str) or not _F_ID_RE.match(fid):
            errs.append(f"E-research-finding-id: {fid!r} does not match ^F[1-9][0-9]*$")
    dup = _dupes([i for i in f_ids if isinstance(i, str)])
    if dup:
        errs.append(f"E-research-finding-id-duplicate: {dup}")

    d_ids = [d.get("id") for d in dp_entries]
    for did in d_ids:
        if not isinstance(did, str) or not _D_ID_RE.match(did):
            errs.append(f"E-research-data-point-id: {did!r} does not match ^D[1-9][0-9]*$")
    dup = _dupes([i for i in d_ids if isinstance(i, str)])
    if dup:
        errs.append(f"E-research-data-point-id-duplicate: {dup}")

    s_ids = [s.get("id") for s in source_entries]
    for sid in s_ids:
        if not isinstance(sid, str) or not _S_ID_RE.match(sid):
            errs.append(f"E-research-source-id: {sid!r} does not match ^S[1-9][0-9]*$")
    dup = _dupes([i for i in s_ids if isinstance(i, str)])
    if dup:
        errs.append(f"E-research-source-id-duplicate: {dup}")

    d_id_set = {i for i in d_ids if isinstance(i, str)}
    sources_by_id = {s.get("id"): s for s in source_entries if isinstance(s.get("id"), str)}
    findings_by_id = {f.get("id"): f for f in finding_entries if isinstance(f.get("id"), str)}
    dp_by_id = {d.get("id"): d for d in dp_entries if isinstance(d.get("id"), str)}

    # --- cross-references (spec §5.1): findings <-> sources, data_points <-> sources,
    # findings -> data_points (one-directional: data_points carry no back-pointer list) --
    for f in finding_entries:
        fid = f.get("id")
        dpids = f.get("data_point_ids")
        if not isinstance(dpids, list):
            errs.append(f"E-research-finding-data-point-ids: {fid!r} 'data_point_ids' "
                        f"missing or not a list")
            dpids = []
        for dpid in dpids:
            if not isinstance(dpid, str):
                errs.append(f"E-research-finding-data-point-ids: finding {fid!r} 'data_point_ids' "
                            f"entry {dpid!r} is not a string")
            elif dpid not in d_id_set:
                errs.append(f"E-research-ref-finding-datapoint: finding {fid!r} references "
                            f"unknown data point {dpid!r}")

        sids = f.get("source_ids")
        if not isinstance(sids, list):
            errs.append(f"E-research-finding-source-ids: {fid!r} 'source_ids' missing or not a list")
            sids = []
        for sid in sids:
            if not isinstance(sid, str):
                errs.append(f"E-research-finding-source-ids: finding {fid!r} 'source_ids' "
                            f"entry {sid!r} is not a string")
                continue
            src = sources_by_id.get(sid)
            if src is None:
                errs.append(f"E-research-ref-finding-source: finding {fid!r} references "
                            f"unknown source {sid!r}")
            elif fid not in (src.get("supports_finding_ids") or []):
                errs.append(f"E-research-ref-finding-source: source {sid!r} 'supports_finding_ids' "
                            f"missing back-reference to finding {fid!r}")

    for s in source_entries:
        sid = s.get("id")
        sfids = s.get("supports_finding_ids")
        if not isinstance(sfids, list):
            errs.append(f"E-research-source-supports-finding-ids: {sid!r} 'supports_finding_ids' "
                        f"missing or not a list")
            sfids = []
        for fid in sfids:
            if not isinstance(fid, str):
                errs.append(f"E-research-source-supports-finding-ids: source {sid!r} "
                            f"'supports_finding_ids' entry {fid!r} is not a string")
                continue
            fnd = findings_by_id.get(fid)
            if fnd is None:
                errs.append(f"E-research-ref-finding-source: source {sid!r} references "
                            f"unknown finding {fid!r}")
            elif sid not in (fnd.get("source_ids") or []):
                errs.append(f"E-research-ref-finding-source: finding {fid!r} 'source_ids' "
                            f"missing back-reference to source {sid!r}")

        sdpids = s.get("supports_data_point_ids")
        if not isinstance(sdpids, list):
            errs.append(f"E-research-source-supports-data-point-ids: {sid!r} "
                        f"'supports_data_point_ids' missing or not a list")
            sdpids = []
        for dpid in sdpids:
            if not isinstance(dpid, str):
                errs.append(f"E-research-source-supports-data-point-ids: source {sid!r} "
                            f"'supports_data_point_ids' entry {dpid!r} is not a string")
                continue
            dp = dp_by_id.get(dpid)
            if dp is None:
                errs.append(f"E-research-ref-datapoint-source: source {sid!r} references "
                            f"unknown data point {dpid!r}")
            elif dp.get("source_id") != sid:
                errs.append(f"E-research-ref-datapoint-source: data point {dpid!r} 'source_id' "
                            f"does not match source {sid!r}")

    for d in dp_entries:
        did = d.get("id")
        dsid = d.get("source_id")
        if dsid == "":
            continue  # calculated points may carry no external source
        if not isinstance(dsid, str):
            continue  # type checked below alongside the kind-specific rules
        src = sources_by_id.get(dsid)
        if src is None:
            errs.append(f"E-research-ref-datapoint-source: data point {did!r} references "
                        f"unknown source {dsid!r}")
        elif did not in (src.get("supports_data_point_ids") or []):
            errs.append(f"E-research-ref-datapoint-source: source {dsid!r} 'supports_data_point_ids' "
                        f"missing back-reference to data point {did!r}")

    # --- contrary-evidence contract (spec §4): disconfirming_evidence is
    # EITHER a non-empty array of {source_id, finding_id, why_contrary} whose
    # ids resolve in this report's own sources[]/findings[], OR a single
    # {status:'none found', searched:non-empty}. The verification-side
    # cross-check (validate_verification, business_research.validation.
    # verification) additionally requires each array entry's cited source to
    # verify as 'contradicts' for that finding — this function only checks
    # the agent report's own shape and reference resolution.
    disc = doc.get("disconfirming_evidence")
    if isinstance(disc, list):
        if not disc:
            errs.append("E-research-disconfirming-shape: 'disconfirming_evidence' array "
                        "must be non-empty")
        for i, disc_entry in enumerate(disc):
            if not isinstance(disc_entry, dict):
                errs.append(f"E-research-disconfirming-shape: disconfirming_evidence[{i}] "
                            f"is not an object")
                continue
            disc_sid = disc_entry.get("source_id")
            if not isinstance(disc_sid, str) or disc_sid not in sources_by_id:
                errs.append(f"E-research-disconfirming-source-ref: disconfirming_evidence[{i}] "
                            f"source_id {disc_sid!r} does not resolve in sources[]")
            disc_fid = disc_entry.get("finding_id")
            if not isinstance(disc_fid, str) or disc_fid not in findings_by_id:
                errs.append(f"E-research-disconfirming-finding-ref: disconfirming_evidence[{i}] "
                            f"finding_id {disc_fid!r} does not resolve in findings[]")
            why_contrary = disc_entry.get("why_contrary")
            if not isinstance(why_contrary, str) or not why_contrary:
                errs.append(f"E-research-disconfirming-shape: disconfirming_evidence[{i}] "
                            f"missing non-empty 'why_contrary'")
    elif isinstance(disc, dict):
        disc_keys = set(disc.keys())
        if disc_keys != _DISCONFIRMING_NONE_KEYS:
            errs.append(f"E-research-disconfirming-shape: disconfirming_evidence object keys "
                        f"{sorted(disc_keys)} != {sorted(_DISCONFIRMING_NONE_KEYS)}")
        if disc.get("status") != "none found":
            errs.append(f"E-research-disconfirming-shape: disconfirming_evidence status "
                        f"{disc.get('status')!r} != 'none found'")
        searched = disc.get("searched")
        if not isinstance(searched, str) or not searched:
            errs.append("E-research-disconfirming-shape: disconfirming_evidence missing "
                        "non-empty 'searched'")
    else:
        errs.append(f"E-research-disconfirming-shape: 'disconfirming_evidence' must be a "
                    f"non-empty array or {{'status': 'none found', 'searched': ...}}, "
                    f"got {disc!r}")

    # --- data_points: kind literal + kind-specific rules + dimension vocabulary --
    calc_graph: dict[object, list[str]] = {}
    for d in dp_entries:
        did = d.get("id")
        kind = d.get("kind")
        if kind not in _DP_KINDS:
            errs.append(f"E-research-data-point-kind: {did!r} kind {kind!r} not in {_DP_KINDS}")

        # --- nested field hardening: metric/unit/value -----------------------
        # These three feed the renderer's chart/KPI-card layer directly
        # (fmt_num, chart labels/axes); a missing/malformed one there would
        # surface as a raw KeyError/TypeError deep in rendering rather than a
        # named validation error here.
        metric = d.get("metric")
        if not isinstance(metric, str) or not metric:
            errs.append(f"E-research-data-point-metric: {did!r} missing non-empty 'metric'")

        unit = d.get("unit")
        if not isinstance(unit, str) or not unit:
            errs.append(f"E-research-data-point-unit: {did!r} missing non-empty 'unit'")

        value = d.get("value")
        # Explicit isinstance/bool check rather than relying solely on the
        # json.loads parse hooks (load_document's _parse_float/_parse_int):
        # those catch malformed number *tokens* (exponents, extra decimals,
        # NaN/Infinity) but bool is a subclass of int in Python, so a literal
        # `true`/`false` in the JSON source parses to a Python bool and
        # sails through `isinstance(value, int)` unless bool is excluded
        # first. math.isfinite is a second belt-and-braces check: the parse
        # hooks already reject NaN/Infinity at load time, but a value could
        # in principle reach this function via any other caller (e.g. tests
        # constructing dicts directly), not just load_document.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errs.append(f"E-research-data-point-value: {did!r} 'value' must be a non-boolean "
                        f"int/float, got {value!r}")
        elif not math.isfinite(value):
            errs.append(f"E-research-data-point-value: {did!r} 'value' must be finite, "
                        f"got {value!r}")

        inputs = d.get("inputs")
        formula = d.get("formula")

        if kind in ("observed", "estimated"):
            if inputs != []:
                errs.append(f"E-research-data-point-inputs: {did!r} kind={kind!r} requires "
                            f"inputs == [], got {inputs!r}")
            if formula != "":
                errs.append(f"E-research-data-point-formula: {did!r} kind={kind!r} requires "
                            f"formula == '', got {formula!r}")
            sid = d.get("source_id")
            if not isinstance(sid, str) or not sid or sid not in sources_by_id:
                errs.append(f"E-research-data-point-source: {did!r} kind={kind!r} requires a "
                            f"resolving 'source_id', got {sid!r}")

        elif kind == "calculated":
            if not isinstance(inputs, list) or not inputs:
                errs.append(f"E-research-data-point-inputs: {did!r} kind='calculated' requires "
                            f"non-empty inputs, got {inputs!r}")
                inputs = []
            non_str_inputs = [i for i in inputs if not isinstance(i, str)]
            if non_str_inputs:
                errs.append(f"E-research-data-point-inputs: {did!r} inputs entries "
                            f"{non_str_inputs} are not strings")
            str_inputs = [i for i in inputs if isinstance(i, str)]
            bad_inputs = [i for i in str_inputs if i not in d_id_set]
            if bad_inputs:
                errs.append(f"E-research-data-point-inputs: {did!r} inputs reference unknown "
                            f"data points {bad_inputs}")

            if not isinstance(formula, str) or not formula:
                errs.append(f"E-research-data-point-formula: {did!r} kind='calculated' requires "
                            f"a non-empty 'formula', got {formula!r}")
            else:
                ids, ferr = formula_ids(formula)
                if ferr is not None:
                    errs.append(ferr)
                elif ids is not None:
                    extra_refs = ids - set(str_inputs)
                    if extra_refs:
                        errs.append(f"E-research-data-point-formula-refs: {did!r} formula "
                                    f"references {sorted(extra_refs)} not in inputs {inputs}")
                    unused_inputs = set(str_inputs) - ids
                    if unused_inputs:
                        errs.append(f"E-research-formula-unused-input: {did!r} inputs "
                                    f"{sorted(unused_inputs)} declared but not referenced in "
                                    f"formula {formula!r}")

            dp_source_id = d.get("source_id")
            if "source_id" in d and not isinstance(dp_source_id, str):
                errs.append(f"E-research-data-point-source: {did!r} kind={kind!r} "
                            f"'source_id' must be a string, got {dp_source_id!r}")

            calc_graph[did] = [i for i in str_inputs if i in d_id_set]

        period = d.get("period")
        if not isinstance(period, str) or not _PERIOD_RE.match(period):
            errs.append(f"E-research-period: data point {did!r} period {period!r} invalid")

        geography = d.get("geography")
        if not isinstance(geography, str) or not (
                geography in ("global", "not_applicable") or _GEO_RE.match(geography)):
            errs.append(f"E-research-geography: data point {did!r} geography {geography!r} invalid")

    cycle = _find_formula_cycle(calc_graph)
    if cycle is not None:
        errs.append(f"E-research-formula-cycle: cyclic calculated data point dependency {cycle}")

    # --- finding field hardening: claim/topic/confidence -------------------
    # `claim` feeds the renderer's finding markup directly; `topic` is the
    # join key for the manifest's required_topics rule (a missing/wrong-type
    # topic would silently make E-research-required-topic pass or fail for the
    # wrong reason); `confidence` is looked up as `labels["confidence"][x]`
    # in the renderer — an out-of-vocabulary value would be a raw KeyError.
    for f in finding_entries:
        fid = f.get("id")

        claim = f.get("claim")
        if not isinstance(claim, str) or not claim:
            errs.append(f"E-research-finding-claim: {fid!r} missing non-empty 'claim'")

        topic = f.get("topic")
        if not isinstance(topic, str) or not topic:
            errs.append(f"E-research-finding-topic: {fid!r} missing non-empty 'topic'")

        confidence = f.get("confidence")
        if confidence not in _CONFIDENCE_VALUES:
            errs.append(f"E-research-finding-confidence: {fid!r} confidence {confidence!r} "
                        f"not in {_CONFIDENCE_VALUES}")

    # --- doc-level summary: presence + type ---------------------------------
    summary = doc.get("summary")
    if not isinstance(summary, str) or not summary:
        errs.append("E-research-summary: missing non-empty 'summary'")

    # --- quantitative-claim rule (spec §5.1) ------------------------------
    for f in finding_entries:
        fid = f.get("id")
        claim = f.get("claim")
        dpids = f.get("data_point_ids")
        if isinstance(claim, str) and has_numeric_token(claim) and not (
                isinstance(dpids, list) and dpids):
            errs.append(f"E-research-numeric-claim: finding {fid!r} claim carries a numeric "
                        f"token but has no data_point_ids")

    if isinstance(summary, str) and has_numeric_token(summary) and len(dp_entries) == 0:
        errs.append("E-research-numeric-summary: summary carries a numeric token but the "
                    "document has zero data points")

    # --- required topics (from the manifest roster entry) -----------------
    if entry is not None:
        required_topics = entry.get("required_topics")
        if isinstance(required_topics, list):
            finding_topics = {f.get("topic") for f in finding_entries
                              if isinstance(f.get("topic"), str)}
            for topic in required_topics:
                if topic not in finding_topics:
                    errs.append(f"E-research-required-topic: no finding carries required "
                                f"topic {topic!r}")

    # --- caps (from the manifest roster entry) -----------------------------
    if entry is not None:
        caps = entry.get("caps")
        if isinstance(caps, dict):
            if len(findings) > caps.get("findings", 0):
                errs.append(f"E-research-cap-findings: {len(findings)} findings exceeds "
                            f"cap {caps.get('findings')}")
            if len(sources) > caps.get("sources", 0):
                errs.append(f"E-research-cap-sources: {len(sources)} sources exceeds "
                            f"cap {caps.get('sources')}")
            if len(data_points) > caps.get("data_points", 0):
                errs.append(f"E-research-cap-data-points: {len(data_points)} data_points exceeds "
                            f"cap {caps.get('data_points')}")
            byte_size = len(json.dumps(doc, ensure_ascii=False).encode())
            if byte_size > caps.get("bytes", 0):
                errs.append(f"E-research-cap-bytes: {byte_size} bytes exceeds cap {caps.get('bytes')}")

    # --- sources: URL scheme, required text fields, dates ------------------
    manifest_report_date = manifest.get("report_date") if isinstance(manifest, dict) else None
    report_date_ok = isinstance(manifest_report_date, str) and bool(_DATE_RE.match(manifest_report_date))
    if not report_date_ok:
        errs.append("E-research-manifest-report-date: manifest report_date malformed, "
                    "cannot compare accessed_at")
    for s in source_entries:
        sid = s.get("id")
        url = s.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            errs.append(f"E-research-source-url: source {sid!r} url {url!r} must start with https://")

        if not isinstance(s.get("title"), str) or not s.get("title"):
            errs.append(f"E-research-source-title: source {sid!r} missing non-empty title")

        if not isinstance(s.get("publisher"), str) or not s.get("publisher"):
            errs.append(f"E-research-source-publisher: source {sid!r} missing non-empty publisher")

        if not isinstance(s.get("usage"), str) or not s.get("usage"):
            errs.append(f"E-research-source-usage: source {sid!r} missing non-empty usage")

        accessed_at = s.get("accessed_at")
        if not isinstance(accessed_at, str) or not _DATE_RE.match(accessed_at):
            errs.append(f"E-research-source-date: source {sid!r} accessed_at {accessed_at!r} "
                        f"is not YYYY-MM-DD")
        elif (report_date_ok and isinstance(manifest_report_date, str)
                and accessed_at > manifest_report_date):
            errs.append(f"E-research-source-date-future: source {sid!r} accessed_at "
                        f"{accessed_at!r} is after manifest report_date {manifest_report_date!r}")

    return errs
