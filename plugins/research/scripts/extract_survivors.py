#!/usr/bin/env python3
"""Verified-id + disputed-summary extractor CLI. Stdlib only.
Contract: docs/research/specs/2026-07-12-business-research-flow-redesign-hookfree-design.md
§6 ("verified-id handoff (token fix)").

Reads every surviving agent's verification document on the orchestrator's
behalf — under `surviving_attempts` (business_research.validation.verification,
reused unmodified: this module does not reimplement survivor resolution) —
and emits a single compact JSON summary on stdout: per surviving agent, its
verification file's path (relative to `--build-dir`), the ids of every
`verified` finding/data point, and a one-line summary per `disputed` finding/
data point. The orchestrator consumes this instead of reading every
verification file into its own context.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from business_research.json_io import load_document
from business_research.validation.verification import surviving_attempts

__all__ = ["build_survivors_summary", "extract_verified_and_disputed", "main"]


def _summary_for(item: Mapping[str, object]) -> str:
    """One-line summary for a `disputed` finding/data point: the first
    `supports` locator and the first `contradicts` locator, side by side —
    that pairing is the actual content of a dispute (mixed evidence), so it
    is more useful than either side alone. Falls back to a short id-derived
    string when the item carries no usable evidence locator (e.g. a
    synthetic/degenerate fixture), keeping the summary always non-empty and
    deterministic."""
    evidence = item.get("evidence")
    evidence = evidence if isinstance(evidence, list) else []

    def _first_locator(verdict: str) -> str | None:
        for e in evidence:
            if not isinstance(e, dict) or e.get("verdict") != verdict:
                continue
            locator = e.get("evidence_locator")
            if isinstance(locator, str) and locator:
                return locator
        return None

    parts = []
    supports = _first_locator("supports")
    if supports is not None:
        parts.append(f"supports: {supports}")
    contradicts = _first_locator("contradicts")
    if contradicts is not None:
        parts.append(f"contradicts: {contradicts}")
    if parts:
        return "; ".join(parts)

    item_id = item.get("id")
    return f"{item_id} disputed" if isinstance(item_id, str) else "disputed"


def _verdict_ids(items: object, verdict: str) -> list[str]:
    items = items if isinstance(items, list) else []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict) or item.get("verdict") != verdict:
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            ids.append(item_id)
    return ids


def _disputed_entries(items: object) -> list[dict[str, str]]:
    items = items if isinstance(items, list) else []
    entries: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("verdict") != "disputed":
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            entries.append({"id": item_id, "summary": _summary_for(item)})
    return entries


def extract_verified_and_disputed(
    verification_doc: Mapping[str, object],
) -> tuple[list[str], list[dict[str, str]]]:
    """Pure extraction over a single already-loaded verification document —
    no file I/O, no survival gate. Findings and data points are walked and
    concatenated, then each output list is sorted ascending by id string (the
    plan's "roster order, then id order" AC) — findings and data points may
    therefore interleave in the result; sorting the concatenation once is
    simpler than a merge and yields the same deterministic ascending-id
    output."""
    findings = verification_doc.get("findings")
    data_points = verification_doc.get("data_points")

    verified = _verdict_ids(findings, "verified") + _verdict_ids(data_points, "verified")
    disputed = _disputed_entries(findings) + _disputed_entries(data_points)
    verified.sort()
    disputed.sort(key=lambda entry: entry["id"])
    return verified, disputed


def build_survivors_summary(build_dir: str, manifest: Mapping[str, object]) -> dict[str, Any]:
    """The full `{"survivors": [...]}` payload (Task 11 interface). Walks the
    manifest roster in order — not the `surviving_attempts` dict's own
    (insertion) order, which happens to match today but is not a contract —
    so output ordering is deterministic on the manifest alone."""
    survivors = surviving_attempts(build_dir, manifest)
    raw_roster = manifest.get("roster") if isinstance(manifest, dict) else None
    roster: Sequence[object] = raw_roster if isinstance(raw_roster, list) else []

    out: list[dict[str, Any]] = []
    for entry in roster:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("id")
        if not isinstance(pid, str):
            continue

        survivor = survivors.get(pid)
        if survivor is None:
            continue
        verification = survivor["verification"]
        if not isinstance(verification, dict):
            continue

        verified, disputed = extract_verified_and_disputed(verification)
        out.append({
            "agent": pid,
            "verification_path": f"verification/{pid}.a{survivor['attempt']}.json",
            "verified": verified,
            "disputed": disputed,
        })

    return {"survivors": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)

    manifest_doc, errs = load_document(args.manifest)
    if manifest_doc is None or errs or not isinstance(manifest_doc, dict):
        if not errs:
            errs = [f"E-manifest-doc-type: {args.manifest} did not load as a JSON object"]
        print("\n".join(errs))
        return 1

    summary = build_survivors_summary(args.build_dir, manifest_doc)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
