"""JSON document contracts for the business-research pipeline (V2 spec
docs/research/specs/2026-07-10-business-research-v2-html-design.md §5-§6).

These TypedDicts describe documents AFTER validate_business_json.py has
accepted them. The validators themselves work on raw dicts and must not
assume this shape.

Fields typed `Literal[...]` are closed vocabularies the corresponding
validate_* function checks with `in <tuple>` / `!=` against an exact string —
those Literals are guarantees for a document that passed validation, not
guesses. Everything else is `str`/`int`/`float`/`list`/`dict` as the shape
requires. Every TypedDict here is `total=True` (all keys always present in a
validated document) except `PanelDataPoint.source_id`, which
`validate_panel` explicitly allows to be absent for `kind="calculated"`.
"""
from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

__all__ = [
    "CAPS_QUANT",
    "CAPS_STANDARD",
    "CONDITIONAL_ROSTER",
    "CORE_ROSTER",
    "QUANT_ROLES",
    "REQUIRED_TOPICS",
    "SynthesisRef",
    "RosterEntry",
    "ManifestDoc",
    "EnvelopeSource",
    "EnvelopeRegistry",
    "EnvelopeDoc",
    "PanelSource",
    "PanelFinding",
    "PanelDataPoint",
    "PanelDoc",
    "EvidenceEntry",
    "VerificationSource",
    "VerificationItem",
    "VerificationAdditionalSource",
    "VerificationDoc",
    "SynthesisVerdict",
    "SynthesisRefItem",
    "SynthesisRisk",
    "SynthesisRecommendation",
    "SynthesisSection",
    "SynthesisDoc",
]

# --- Roster / caps constants (spec §6; moved from validate_business_json.py
# lines 21-34 — values verbatim; CORE_ROSTER/QUANT_ROLES converted
# list->tuple / set->frozenset per this module's export contract, same
# ids/roles/values, immutable container types) ---

CORE_ROSTER: tuple[str, ...] = (
    "market-researcher", "product-manager", "business-analyst",
    "trend-analyst", "competitive-analyst", "risk-manager",
    "pricing-monetization", "gtm-channels", "unit-economics",
)
QUANT_ROLES: frozenset[str] = frozenset({
    "market-researcher", "pricing-monetization", "gtm-channels", "unit-economics",
})
CAPS_STANDARD: dict[str, int] = {"findings": 4, "sources": 6, "data_points": 8, "bytes": 8000}
CAPS_QUANT: dict[str, int] = {"findings": 4, "sources": 8, "data_points": 12, "bytes": 10000}
CONDITIONAL_ROSTER: list[str] = ["legal-advisor", "project-idea-validator", "ux-researcher"]

# Required topics per role, closed mapping (spec §5.1, §6): trend-analyst
# must carry >=1 finding tagged "timing", competitive-analyst "moat"; every
# other role carries none.
REQUIRED_TOPICS: dict[str, list[str]] = {
    "trend-analyst": ["timing"], "competitive-analyst": ["moat"],
}

# --- Synthesis ref grammar (spec §5.4) ---------------------------------------

# A qualified reference string '<panelist-id>:F<n>' or '<panelist-id>:D<n>',
# as it appears in every 'refs' array throughout a synthesis document. Plain
# string, not dict-shaped — matched by validate_synthesis's _REF_RE.
type SynthesisRef = str


# --- manifest kind (spec §6) --------------------------------------------------

class RosterEntry(TypedDict):
    id: str
    kind: str                 # "core" | "conditional" — validate_manifest checks
                               # it agrees with the id's membership in
                               # CORE_ROSTER/CONDITIONAL_ROSTER
    selection_rule: str        # "always" for core; non-empty (e.g. "keyword:<...>")
                               # for conditional — both enforced by validate_manifest
    model: str
    quantitative: bool
    caps: dict[str, int]
    required_topics: list[str]


class ManifestDoc(TypedDict):
    schema_version: Literal["business-research-run-v2"]
    slug: str
    brief: str
    report_date: str
    language: Literal["ru", "en"]
    build_dir: str
    final_report_path: str
    roster: list[RosterEntry]


# --- envelope kind (spec §5.2) ------------------------------------------------

class EnvelopeSource(TypedDict):
    id: str
    url: str
    title: str
    publisher: str
    accessed_at: str
    status: Literal["verified", "unverified"]


class EnvelopeRegistry(TypedDict):
    """The envelope's 'registry' key — a nested 'fact-pack-sources-v1'
    sub-document, not a bare list. (The original skeleton for this task
    guessed `registry: list[EnvelopeSource]`; validate_envelope requires
    `doc["registry"]` to be an object carrying its own schema_version/slug/
    facts_digest plus the `sources` list — corrected against source.)"""
    schema_version: Literal["fact-pack-sources-v1"]
    slug: str
    facts_digest: str
    sources: list[EnvelopeSource]


class EnvelopeDoc(TypedDict):
    schema_version: Literal["fact-pack-envelope-v1"]
    facts_path: str
    registry: EnvelopeRegistry


# --- panel kind (spec §5.1) ---------------------------------------------------

class PanelSource(TypedDict):
    id: str
    url: str
    title: str
    publisher: str
    accessed_at: str
    usage: str
    supports_finding_ids: list[str]
    supports_data_point_ids: list[str]


class PanelFinding(TypedDict):
    id: str
    topic: str
    claim: str
    confidence: Literal["high", "medium", "low"]
    source_ids: list[str]
    data_point_ids: list[str]


class PanelDataPoint(TypedDict):
    id: str
    metric: str
    value: float
    unit: str
    period: str
    geography: str
    source_id: NotRequired[str]  # required + must resolve for kind in
                                  # observed/estimated; may be absent for calculated
    kind: Literal["observed", "estimated", "calculated"]
    inputs: list[str]            # [] for observed/estimated; non-empty D-ids for calculated
    formula: str                  # "" for observed/estimated; non-empty parseable
                                    # expr for calculated


class PanelDoc(TypedDict):
    schema_version: Literal["business-panel-v2"]
    panelist: str
    status: Literal["complete"]
    summary: str
    findings: list[PanelFinding]
    data_points: list[PanelDataPoint]
    sources: list[PanelSource]
    limitations: list[str]


# --- verification kind (spec §5.3) --------------------------------------------

class EvidenceEntry(TypedDict):
    source_id: str
    verdict: Literal["supports", "contradicts", "unrelated", "unreachable"]
    evidence_locator: str


class VerificationSource(TypedDict):
    id: str
    reachability: Literal["reachable", "blocked", "dead"]


class VerificationItem(TypedDict):
    """Shared shape of one `findings[]` / `data_points[]` entry in a
    verification document."""
    id: str
    evidence: list[EvidenceEntry]
    verdict: Literal["verified", "contradicted", "unsupported"]


class VerificationAdditionalSource(TypedDict):
    id: str
    url: str
    title: str
    publisher: str
    accessed_at: str
    usage: str
    relates_to: list[str]


class VerificationDoc(TypedDict):
    schema_version: Literal["business-verification-v1"]
    panelist: str
    attempt: int
    verifier_status: Literal["complete"]
    sources: list[VerificationSource]
    findings: list[VerificationItem]
    data_points: list[VerificationItem]
    additional_sources: list[VerificationAdditionalSource]


# --- synthesis kind (spec §5.4) ------------------------------------------------

class SynthesisVerdict(TypedDict):
    decision: Literal["go", "no-go", "conditional-go", "insufficient-evidence"]
    statement: str
    confidence: Literal["high", "medium", "low"]
    refs: list[SynthesisRef]


class SynthesisRefItem(TypedDict):
    """Shared {text, refs} shape: executive_summary[], limitations[],
    sections[].narrative[], sections[].disagreements[]."""
    text: str
    refs: list[SynthesisRef]


class SynthesisRisk(TypedDict):
    risk: str
    severity: Literal["high", "medium", "low"]
    refs: list[SynthesisRef]


class SynthesisRecommendation(TypedDict):
    recommendation: str
    refs: list[SynthesisRef]


class SynthesisSection(TypedDict):
    panelist: str
    narrative: list[SynthesisRefItem]
    disagreements: list[SynthesisRefItem]


class SynthesisDoc(TypedDict):
    schema_version: Literal["business-synthesis-v1"]
    slug: str
    title: str
    verdict: SynthesisVerdict
    executive_summary: list[SynthesisRefItem]
    sections: list[SynthesisSection]
    risks: list[SynthesisRisk]
    recommendations: list[SynthesisRecommendation]
    limitations: list[SynthesisRefItem]
