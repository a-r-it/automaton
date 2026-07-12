"""Run loading, HTML assembly, provenance (V2 spec §8)."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from business_research import json_io
from business_research.models import (
    EnvelopeRegistry,
    ManifestDoc,
    PanelDoc,
    SynthesisDoc,
    VerificationDoc,
)
from business_research.rendering.charts import render_kpi_strip
from business_research.rendering.localization import LABELS, _lang, esc
from business_research.rendering.sections import (
    render_exec_summary,
    render_limitations,
    render_methodology,
    render_recommendations,
    render_risks,
    render_section,
)
from business_research.rendering.sources import render_sources
from business_research.validation.envelope import validate_envelope
from business_research.validation.manifest import validate_manifest
from business_research.validation.panel import validate_panel
from business_research.validation.synthesis import validate_synthesis
from business_research.validation.verification import (
    attempt_filename_errors,
    survival_errors,
    surviving_attempts,
    validate_verification,
)

# System font stack, CSS custom properties (light + dark), print rules, and a
# single mobile breakpoint. One constant, embedded verbatim in one <style>
# block (spec §8, §11: zero JavaScript, light/dark via prefers-color-scheme,
# print CSS with section page breaks, responsive single column on mobile).
PAGE_CSS = """
:root {
  --font-sans: -apple-system, "Segoe UI", Roboto, sans-serif;
  --color-bg: #ffffff;
  --color-fg: #1a1a1a;
  --color-muted: #5a6472;
  --color-border: #d8dee4;
  --color-card-bg: #f6f8fa;
  --color-accent: #2563eb;
  --color-verdict-go-bg: #16a34a;
  --color-verdict-no-go-bg: #dc2626;
  --color-verdict-conditional-go-bg: #d97706;
  --color-verdict-insufficient-evidence-bg: #6b7280;
  --color-verdict-fg: #ffffff;
  --color-severity-high: #dc2626;
  --color-severity-medium: #d97706;
  --color-severity-low: #16a34a;
  --color-confidence-high: #2563eb;
  --color-confidence-medium: #7c8ba1;
  --color-confidence-low: #9aa4b2;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0f1115;
    --color-fg: #e6e8eb;
    --color-muted: #9aa4b2;
    --color-border: #2a2f37;
    --color-card-bg: #171a20;
    --color-accent: #60a5fa;
    --color-confidence-high: #60a5fa;
    --color-confidence-medium: #94a3b8;
    --color-confidence-low: #64748b;
  }
}

* { box-sizing: border-box; }

html { color-scheme: light dark; }

body {
  margin: 0;
  padding: 2rem;
  font-family: var(--font-sans);
  background: var(--color-bg);
  color: var(--color-fg);
  line-height: 1.5;
  max-width: 960px;
  margin-inline: auto;
}

header.report-header {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 1rem;
  margin-bottom: 1.5rem;
}

header.report-header h1 { margin: 0 0 0.5rem; font-size: 1.75rem; }

.report-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  color: var(--color-muted);
  font-size: 0.9rem;
}

.verdict-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--color-verdict-fg);
}
.verdict-go { background: var(--color-verdict-go-bg); }
.verdict-no-go { background: var(--color-verdict-no-go-bg); }
.verdict-conditional-go { background: var(--color-verdict-conditional-go-bg); }
.verdict-insufficient-evidence { background: var(--color-verdict-insufficient-evidence-bg); }

section { margin-bottom: 2rem; }

details > summary { cursor: pointer; font-weight: 600; }

.report-section > details > summary { font-size: 1.25rem; }

.section-body { margin-top: 0.75rem; }

.card {
  border: 1px solid var(--color-border);
  background: var(--color-card-bg);
  border-radius: 0.5rem;
  padding: 1rem;
}

.confidence-badge, .severity-badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-verdict-fg);
  margin-right: 0.5rem;
}
.confidence-high { background: var(--color-confidence-high); }
.confidence-medium { background: var(--color-confidence-medium); }
.confidence-low { background: var(--color-confidence-low); }
.severity-high { background: var(--color-severity-high); }
.severity-medium { background: var(--color-severity-medium); }
.severity-low { background: var(--color-severity-low); }

.finding {
  border-left: 3px solid var(--color-border);
  padding: 0.5rem 0.75rem;
  margin: 0.75rem 0;
}
.finding-claim { margin: 0.35rem 0; }
.finding-sources { color: var(--color-muted); font-size: 0.85rem; }

.disagreement-callout {
  border-left: 3px solid var(--color-severity-medium);
  background: var(--color-card-bg);
  padding: 0.5rem 0.75rem;
  margin: 0.75rem 0;
}

.risk-item { margin: 0.75rem 0; }

table.methodology-roster { width: 100%; border-collapse: collapse; margin: 0.75rem 0; }
table.methodology-roster th, table.methodology-roster td {
  text-align: left;
  padding: 0.35rem 0.6rem;
  border-bottom: 1px solid var(--color-border);
}
.methodology-counts { padding-left: 1.25rem; }

.source-entry { border-bottom: 1px solid var(--color-border); padding: 0.6rem 0; }
.source-title a { color: var(--color-accent); }
.source-mentions {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.85rem;
  color: var(--color-muted);
}
.tag {
  display: inline-block;
  padding: 0 0.4rem;
  border-radius: 0.25rem;
  background: var(--color-card-bg);
  border: 1px solid var(--color-border);
  font-size: 0.75rem;
  margin-right: 0.35rem;
}

sup.ref { font-size: 0.7em; margin-left: 0.15em; }
sup.ref a { color: var(--color-accent); text-decoration: none; }

.section-charts {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin: 0.75rem 0;
}
.chart { flex: 1 1 320px; min-width: 0; }
.chart-title { margin: 0 0 0.35rem; font-size: 0.9rem; font-weight: 600; }
.chart-svg { width: 100%; height: auto; display: block; color: var(--color-fg); }
.chart-footer { margin: 0.35rem 0 0; font-size: 0.8rem; color: var(--color-muted); }

#kpi-strip .section-body { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.kpi-card {
  border: 1px solid var(--color-border);
  background: var(--color-card-bg);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  flex: 1 1 200px;
  min-width: 0;
}
.kpi-metric { margin: 0; font-size: 0.8rem; color: var(--color-muted); }
.kpi-value { margin: 0.2rem 0; font-size: 1.4rem; font-weight: 700; }
.kpi-dims { margin: 0; font-size: 0.8rem; color: var(--color-muted); }
.kpi-footer { margin: 0.35rem 0 0; font-size: 0.75rem; color: var(--color-muted); }

[id] { scroll-margin-top: 1rem; }
.finding:target, .source-entry:target, .kpi-card:target {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

@media print {
  body { padding: 0; max-width: none; }
  section { break-inside: avoid; page-break-inside: avoid; }
  /* !important: de-emphasizing every link on paper must win regardless of
     any more-specific in-content color rule (sup.ref a, .source-title a, ...) */
  a { color: inherit !important; text-decoration: none !important; }
}

@media (max-width: 640px) {
  body { padding: 1rem; }
  .report-meta { flex-direction: column; align-items: flex-start; gap: 0.35rem; }
}
"""

# Provenance JSON escaping (spec §7): after canonical json.dumps, replace the
# three characters that could break out of a <script type="application/json">
# raw-text block with their six-character JSON unicode escapes.
_JSON_ESC = {ord("<"): "\\u003c", ord(">"): "\\u003e", ord("&"): "\\u0026"}


class RenderInputError(Exception):
    """Raised by `load_run` when any staged artifact fails re-validation.
    Carries pre-formatted 'E-render-input: <file>: <error>' lines — the CLI
    prints them verbatim (exit 1, output file never written)."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__("\n".join(lines))
        self.lines = lines


class Survivor(TypedDict):
    """One roster panelist's surviving attempt, as `load_run` re-shapes it
    for `Run.survivors` — narrower than `verification.surviving_attempts`'
    own `_Survivor` (that one also carries `superseded`, typed `object` for
    `panel`/`verification` since it's built before this module's own strict
    turn). By the time a value reaches here it has already passed
    `validate_panel`/`validate_verification`, so `PanelDoc`/`VerificationDoc`
    are the honest types, not `object`."""

    attempt: int
    panel: PanelDoc
    verification: VerificationDoc


@dataclass(frozen=True, slots=True)
class Run:
    """A fully loaded and re-validated build dir, ready to render.

    `survivors` is keyed by roster panelist id, each value a `Survivor`
    (`{"attempt": int, "panel": PanelDoc, "verification": VerificationDoc}`)
    — every roster entry is guaranteed present (load_run raises otherwise).
    `superseded` is the flat, deterministic (roster order, then filename)
    list of every non-surviving attempt filename, for the provenance block.
    """

    manifest: ManifestDoc
    facts_text: str
    facts_digest: str
    registry: EnvelopeRegistry
    survivors: dict[str, Survivor]
    synthesis: SynthesisDoc
    superseded: list[str]




def provenance_block(payload: Mapping[str, object]) -> str:
    """Canonical, deterministic JSON serialization for the embedded
    provenance block (spec §7): sorted keys, compact separators, then the
    JSON string's `<`, `>`, `&` characters replaced by their six-character
    unicode escapes. This is what makes it safe to embed the result verbatim
    inside `<script type="application/json">` regardless of what LLM- or
    web-derived text the payload carries — a literal `</script>` in any
    string value can never survive as `<`/`>` characters. `Mapping[str,
    object]` rather than `ProvenancePayload` itself: the test suite also
    calls this directly with ad hoc dict literals (round-trip/escaping
    tests), and json.dumps' own boundary is genuinely payload-shape-agnostic
    — `_provenance_payload`'s `ProvenancePayload` return is a valid
    `Mapping[str, object]` regardless."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).translate(_JSON_ESC)


def load_run(build_dir: str) -> Run:
    """Loads and re-validates every staged artifact under `build_dir` (spec
    §4 layout): manifest -> facts.md -> facts.sources.json (registry) ->
    surviving attempts per roster entry -> synthesis. Raises
    `RenderInputError` on any invalid input; never returns a partial `Run`."""
    build_path = Path(build_dir)

    manifest_doc, manifest_load_errs = json_io.load_document(build_path / "manifest.json")
    if manifest_doc is None:
        raise RenderInputError(_input_errors("manifest.json", manifest_load_errs))
    manifest_errs = manifest_load_errs + validate_manifest(manifest_doc)
    if manifest_errs:
        raise RenderInputError(_input_errors("manifest.json", manifest_errs))

    facts_path = build_path / "facts.md"
    try:
        facts_text = facts_path.read_text(encoding="utf-8")
    except OSError as e:
        raise RenderInputError([f"E-render-input: facts.md: {e}"]) from e
    facts_digest = json_io.sha256_file(facts_path)

    registry_doc, registry_load_errs = json_io.load_document(build_path / "facts.sources.json")
    if registry_doc is None:
        raise RenderInputError(_input_errors("facts.sources.json", registry_load_errs))
    envelope_errs = registry_load_errs + _validate_registry(registry_doc, manifest_doc, build_path)
    if envelope_errs:
        raise RenderInputError(_input_errors("facts.sources.json", envelope_errs))

    roster = [e for e in manifest_doc.get("roster", []) if isinstance(e, dict)]
    survivors_raw = surviving_attempts(str(build_path), manifest_doc)
    survivors: dict[str, Survivor] = {}
    superseded: list[str] = []
    survivor_errs: list[str] = []
    for entry in roster:
        pid = entry["id"]
        survivor = survivors_raw.get(pid)
        if survivor is None:
            survivor_errs.extend(_diagnose_missing_survivor(build_path, pid, manifest_doc, entry))
            continue
        # cast: verification._Survivor types panel/verification as `object`
        # (that module is out of Task 16's scope, and was deliberately kept
        # loose in Task 15 to avoid rippling into this file ahead of its own
        # turn) — but by this point survivor["panel"]/["verification"] have
        # already passed validate_panel/validate_verification, so PanelDoc/
        # VerificationDoc are the honest types.
        survivors[pid] = {"attempt": survivor["attempt"],
                           "panel": cast(PanelDoc, survivor["panel"]),
                           "verification": cast(VerificationDoc, survivor["verification"])}
        superseded.extend(survivor["superseded"])
    if survivor_errs:
        raise RenderInputError(survivor_errs)

    synthesis_doc, synthesis_load_errs = json_io.load_document(build_path / "synthesis.json")
    if synthesis_doc is None:
        raise RenderInputError(_input_errors("synthesis.json", synthesis_load_errs))
    synthesis_errs = (synthesis_load_errs
                       + validate_synthesis(synthesis_doc, str(build_path)))
    if synthesis_errs:
        raise RenderInputError(_input_errors("synthesis.json", synthesis_errs))

    return Run(manifest=manifest_doc, facts_text=facts_text, facts_digest=facts_digest,
               registry=registry_doc, survivors=survivors, synthesis=synthesis_doc,
               superseded=superseded)


def render(run: Run) -> str:
    """Composes the full single-file HTML report: doctype, head (charset,
    viewport, title, one <style> block), body (header with verdict badge,
    section slots in manifest roster order, embedded provenance block)."""
    manifest = run.manifest
    lang = _lang(run.manifest)
    title = run.synthesis["title"]  # validated non-empty by validate_synthesis

    roster = [e for e in manifest.get("roster", []) if isinstance(e, dict)]
    section_ids = [e["id"] for e in roster if e["id"] in run.survivors]
    dp_anchors = _all_dp_anchor_ids(run)

    body = "".join([
        _render_header(run, lang),
        render_exec_summary(run, dp_anchors),
        render_methodology(run),
        render_kpi_strip(run),
        *(render_section(run, pid, dp_anchors) for pid in section_ids),
        render_risks(run, dp_anchors),
        render_recommendations(run, dp_anchors),
        render_sources(run),
        render_limitations(run, dp_anchors),
        _render_provenance(run),
    ])

    return (
        "<!doctype html>\n"
        f'<html lang="{esc(lang)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        f"<style>{PAGE_CSS}</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def _input_errors(file_label: str, errors: list[str]) -> list[str]:
    return [f"E-render-input: {file_label}: {e}" for e in errors]


def _validate_registry(registry_doc: object, manifest_doc: object, build_path: Path) -> list[str]:
    """`facts.sources.json` stages the *registry* object (`fact-pack-sources-v1`)
    directly — not the `fact-pack-envelope-v1` wrapper `validate_envelope`
    expects (spec §4 vs §5.2). Wrap it in a synthetic envelope so the tested
    field- and digest-checking logic in `validate_envelope` still applies,
    then add the one cross-check it doesn't do: registry slug == manifest
    slug."""
    synthetic_envelope = {
        "schema_version": "fact-pack-envelope-v1",
        "facts_path": str(build_path / "facts.md"),
        "registry": registry_doc,
    }
    errs = validate_envelope(synthetic_envelope, str(build_path))
    registry_slug = registry_doc.get("slug") if isinstance(registry_doc, dict) else None
    manifest_slug = manifest_doc.get("slug") if isinstance(manifest_doc, dict) else None
    if registry_slug != manifest_slug:
        errs.append(f"E-envelope-registry-slug-mismatch: registry slug {registry_slug!r} "
                    f"does not match manifest slug {manifest_slug!r}")
    return errs


def _diagnose_missing_survivor(build_path: Path, pid: str, manifest: Mapping[str, object],
                                entry: object) -> list[str]:
    """Best-effort diagnostic for a roster panelist with no surviving
    attempt: re-runs panel/verification/survival validation against its
    highest attempt so the E-render-input line names the underlying rule,
    not just the fact that no attempt survived."""
    pattern = re.compile(rf"^{re.escape(pid)}\.a([1-9][0-9]*)\.json$")
    attempt_nums = []
    for pf in sorted((build_path / "panel").glob(f"{pid}.a*.json")):
        m = pattern.match(pf.name)
        if m:
            attempt_nums.append(int(m.group(1)))
    if not attempt_nums:
        return [f"E-render-input: panel/{pid}.a*.json: no attempt files found"]

    n = max(attempt_nums)
    panel_rel = f"panel/{pid}.a{n}.json"
    panel_doc, load_errs = json_io.load_document(build_path / panel_rel)
    if panel_doc is None:
        return _input_errors(panel_rel, load_errs)
    panel_errs = load_errs + validate_panel(panel_doc, manifest)
    if panel_errs:
        return _input_errors(panel_rel, panel_errs)

    verif_rel = f"verification/{pid}.a{n}.json"
    verif_path = build_path / verif_rel
    if not verif_path.exists():
        return [f"E-render-input: {verif_rel}: missing"]
    verif_doc, verif_load_errs = json_io.load_document(verif_path)
    if verif_doc is None:
        return _input_errors(verif_rel, verif_load_errs)
    verif_errs = verif_load_errs + validate_verification(verif_doc, panel_doc)
    if verif_errs:
        return _input_errors(verif_rel, verif_errs)

    attempt_errs = attempt_filename_errors(verif_doc, n)
    if attempt_errs:
        return _input_errors(verif_rel, attempt_errs)

    survival_errs = survival_errors(verif_doc, entry, panel_doc)
    if survival_errs:
        return _input_errors(verif_rel, survival_errs)
    return [f"E-render-input: {verif_rel}: no surviving attempt for {pid!r} (cause undetermined)"]


class ProvenancePayload(TypedDict):
    """Exact shape of the embedded provenance block (spec §7, §4) —
    `_PROVENANCE_KEYS` in `test_renderer_core.py` asserts this same key set
    round-trips through `provenance_block`."""

    manifest: ManifestDoc
    facts_md: str
    facts_digest: str
    registry: EnvelopeRegistry
    panel: dict[str, PanelDoc]
    verification: dict[str, VerificationDoc]
    synthesis: SynthesisDoc
    superseded: list[str]


def _provenance_payload(run: Run) -> ProvenancePayload:
    return {
        "manifest": run.manifest,
        "facts_md": run.facts_text,
        "facts_digest": run.facts_digest,
        "registry": run.registry,
        "panel": {pid: s["panel"] for pid, s in run.survivors.items()},
        "verification": {pid: s["verification"] for pid, s in run.survivors.items()},
        "synthesis": run.synthesis,
        "superseded": run.superseded,
    }


def _render_header(run: Run, lang: str) -> str:
    # manifest/synthesis fields accessed directly (no .get fallback): both
    # were fully validated in load_run, so title/verdict/decision/report_date
    # /slug are all guaranteed present and well-formed at this point. The one
    # exception is the LABELS lookup below, which stays defensive against
    # future drift between the validator's decision literals and this table.
    labels = LABELS[lang]
    decision = run.synthesis["verdict"]["decision"]
    verdict_label = labels["verdict_decision"].get(decision, decision)
    title = run.synthesis["title"]
    report_date = run.manifest["report_date"]
    slug = run.manifest["slug"]
    return (
        '<header class="report-header">'
        f"<h1>{esc(title)}</h1>"
        '<p class="report-meta">'
        f'<span class="report-date">{esc(report_date)}</span>'
        f'<span class="report-slug">{esc(slug)}</span>'
        f'<span class="verdict-badge verdict-{esc(decision)}">{esc(verdict_label)}</span>'
        "</p>"
        "</header>"
    )


def _render_provenance(run: Run) -> str:
    return (f'<script type="application/json" id="provenance">'
            f"{provenance_block(_provenance_payload(run))}</script>")


def _all_dp_anchor_ids(run: Run) -> frozenset[str]:
    """Every `id="dp-<panelist>-D<n>"` anchor the render will produce
    somewhere in the document: `_global_kpi_pool` guarantees each panelist's
    verified data points render in exactly one of three places (their own
    chart, the top-level strip, or their own section's leftover cards), so
    this reduces to every surviving attempt's verified data-point ids,
    qualified — no need to actually run `group_charts` again here."""
    ids: set[str] = set()
    for pid, survivor in run.survivors.items():
        for d in survivor["verification"]["data_points"]:
            if d["verdict"] == "verified":
                ids.add(f"dp-{pid}-{d['id']}")
    return frozenset(ids)
