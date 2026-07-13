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
from collections.abc import Callable
from pathlib import Path
from typing import Any

from business_research.json_io import load_document
from business_research.validation.agent import _find_roster_entry, validate_agent
from business_research.validation.manifest import validate_manifest
from business_research.validation.scope import (
    scope_digest,
    validate_manifest_scope_link,
    validate_scope,
)
from business_research.validation.synthesis import validate_synthesis
from business_research.validation.verification import (
    attempt_filename_errors,
    attempt_number_from_filename,
    survival_errors,
    validate_verification,
)


# --- CLI -----------------------------------------------------------------------

def _run_manifest(doc: Any, args: argparse.Namespace) -> list[str]:
    """kind 'manifest': `validate_manifest` alone, unchanged — this is the
    plain doc-only path research/verification/survival's own manifest
    dependency-validation relies on (no build dir, no scope file). `doc`
    is `Any` here, matching main()'s `load_document` boundary (see that
    function's docstring) and the inline lambda this replaces.

    An optional `--scope <path>` additionally runs the build-dir/scope-aware
    cross-check (`validate_manifest_scope_link`) that anchors the stamped
    `scope_digest` to the real scope.json content — additive, never invoked
    when `--scope` is omitted.
    """
    errs = validate_manifest(doc)
    if args.scope:
        scope_doc, scope_load_errs = load_document(args.scope)
        if scope_doc is None:
            return errs + scope_load_errs
        errs = errs + scope_load_errs + validate_manifest_scope_link(doc, scope_doc)
    return errs


def _run_research(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.manifest:
        return ["E-research-manifest-required: --manifest is required for kind 'research'"]
    manifest_doc, load_errs = load_document(args.manifest)
    if manifest_doc is None:
        return load_errs
    manifest_errs = load_errs + validate_manifest(manifest_doc)
    if manifest_errs:
        return manifest_errs
    expected = Path(args.file).name.split(".")[0]
    return validate_agent(doc, manifest_doc, expected_agent=expected)


def _run_verification(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.panel:
        return ["E-verif-panel-required: --panel is required for kind 'verification'"]
    if not args.manifest:
        return ["E-verif-manifest-required: --manifest is required for kind 'verification'"]
    agent_doc, agent_load_errs = load_document(args.panel)
    if agent_load_errs:
        return agent_load_errs
    manifest_doc, manifest_load_errs = load_document(args.manifest)
    if manifest_doc is None:
        return manifest_load_errs
    manifest_errs = manifest_load_errs + validate_manifest(manifest_doc)
    if manifest_errs:
        return manifest_errs
    expected = Path(args.file).name.split(".")[0]
    errs = validate_verification(doc, agent_doc, manifest_doc, expected_agent=expected)
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
    agent_doc, agent_load_errs = load_document(args.panel)
    if agent_load_errs:
        return agent_load_errs
    agent_errs = validate_agent(agent_doc, manifest_doc)
    if agent_errs:
        return agent_errs
    agent_id = doc.get("agent") if isinstance(doc, dict) else None
    entry = _find_roster_entry(manifest_doc, agent_id) if isinstance(agent_id, str) else None
    if entry is None:
        return [f"E-survival-unknown-agent: {agent_id!r} not found in manifest roster"]
    return survival_errors(doc, entry, agent_doc)


def _run_synthesis(doc: object, args: argparse.Namespace) -> list[str]:
    if not args.build_dir:
        return ["E-synth-build-dir-required: --build-dir is required for kind 'synthesis'"]
    return validate_synthesis(doc, args.build_dir)


DISPATCH: dict[str, Callable[[Any, argparse.Namespace], list[str]]] = {
    "manifest": _run_manifest,
    "research": _run_research,
    "verification": _run_verification,
    "synthesis": _run_synthesis,
    "survival": _run_survival,
    "scope": lambda doc, args: validate_scope(doc),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["manifest", "research", "verification",
                                      "synthesis", "survival", "scope"])
    ap.add_argument("file")
    ap.add_argument("--manifest")
    ap.add_argument("--panel")
    ap.add_argument("--build-dir")
    ap.add_argument("--scope",
                     help="kind 'manifest' only: path to scope.json; when given, "
                          "additionally cross-checks the manifest's scope_digest "
                          "(and slug) against the actual scope.json content")
    ap.add_argument("--emit-digest", action="store_true",
                     help="kind 'scope' only: on a valid document, print just its "
                          "scope_digest to stdout instead of nothing")
    a = ap.parse_args(argv)
    doc, errs = load_document(a.file)
    if doc is not None:
        errs = errs + DISPATCH[a.kind](doc, a)
    if a.emit_digest and a.kind == "scope":
        if errs:
            print("\n".join(errs))
            return 1
        print(scope_digest(doc))
        return 0
    print("\n".join(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
