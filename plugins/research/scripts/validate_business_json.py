#!/usr/bin/env python3
"""Mechanical validator CLI for business-research V2 artifacts. Stdlib only.
Contract: docs/research/specs/2026-07-10-business-research-v2-html-design.md §5-§6.
Exit 0 = valid. Exit 1 = one 'E-<rule>: <detail>' line per failure on stdout.

This module is import-clean: importing it has no side effects. It is a thin
CLI over `business_research.validation.*` — the renderer imports those
packages directly (no dependency on this file), so everything imported below
exists solely for this file's own `_run_*`/DISPATCH entries.
"""
from __future__ import annotations

import argparse
import sys

from business_research.json_io import load_document
from business_research.validation.envelope import validate_envelope
from business_research.validation.manifest import validate_manifest
from business_research.validation.panel import _find_roster_entry, validate_panel
from business_research.validation.synthesis import validate_synthesis
from business_research.validation.verification import (
    attempt_filename_errors,
    attempt_number_from_filename,
    survival_errors,
    validate_verification,
)


# --- CLI -----------------------------------------------------------------------

def _run_panel(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.manifest:
        return ["E-panel-manifest-required: --manifest is required for kind 'panel'"]
    manifest_doc, load_errs = load_document(args.manifest)
    if manifest_doc is None:
        return load_errs
    manifest_errs = load_errs + validate_manifest(manifest_doc)
    if manifest_errs:
        return manifest_errs
    return validate_panel(doc, manifest_doc)


def _run_verification(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.panel:
        return ["E-verif-panel-required: --panel is required for kind 'verification'"]
    panel_doc, panel_load_errs = load_document(args.panel)
    if panel_load_errs:
        return panel_load_errs
    errs = validate_verification(doc, panel_doc)
    # Attempt<->filename cross-check (spec §4), CLI-only: `surviving_attempts`
    # already runs this same check when walking build-dir files directly, but
    # a standalone `verification <file> --panel <file>` invocation has no
    # build_dir — pragmatically derive N from the verification file's own
    # name first (that's the document actually being validated), falling
    # back to --panel's filename when the verification path itself doesn't
    # carry the `a<N>.json` pattern. Skipped entirely when neither does, so
    # ad hoc test fixtures outside that naming convention are unaffected.
    n = attempt_number_from_filename(args.file) or attempt_number_from_filename(args.panel)
    if n is not None and isinstance(doc, dict):
        errs = errs + attempt_filename_errors(doc, n)
    return errs


def _run_survival(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.manifest:
        return ["E-survival-manifest-required: --manifest is required for kind 'survival'"]
    if not args.panel:
        return ["E-survival-panel-required: --panel is required for kind 'survival'"]
    manifest_doc, load_errs = load_document(args.manifest)
    if manifest_doc is None:
        return load_errs
    manifest_errs = load_errs + validate_manifest(manifest_doc)
    if manifest_errs:
        return manifest_errs
    panel_doc, panel_load_errs = load_document(args.panel)
    if panel_load_errs:
        return panel_load_errs
    panel_errs = validate_panel(panel_doc, manifest_doc)
    if panel_errs:
        return panel_errs
    panelist = doc.get("panelist") if isinstance(doc, dict) else None
    entry = _find_roster_entry(manifest_doc, panelist) if isinstance(panelist, str) else None
    if entry is None:
        return [f"E-survival-unknown-panelist: {panelist!r} not found in manifest roster"]
    return survival_errors(doc, entry, panel_doc)


def _run_synthesis(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.build_dir:
        return ["E-synth-build-dir-required: --build-dir is required for kind 'synthesis'"]
    return validate_synthesis(doc, args.build_dir)


DISPATCH = {
    "manifest": lambda doc, args: validate_manifest(doc),
    "envelope": lambda doc, args: validate_envelope(doc, args.build_dir),
    "panel": _run_panel,
    "verification": _run_verification,
    "synthesis": _run_synthesis,
    "survival": _run_survival,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["manifest", "envelope", "panel", "verification",
                                      "synthesis", "survival"])
    ap.add_argument("file")
    ap.add_argument("--manifest")
    ap.add_argument("--panel")
    ap.add_argument("--build-dir")
    a = ap.parse_args(argv)
    doc, errs = load_document(a.file)
    if doc is not None:
        errs = errs + DISPATCH[a.kind](doc, a)
    print("\n".join(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
