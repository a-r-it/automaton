"""envelope kind (V2 spec §5.2)."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from business_research.json_io import _DATE_RE, sha256_file

_FP_ID_RE = re.compile(r"^FP[1-9][0-9]*$")
_STATUS_VALUES = ("verified", "unverified")


def validate_envelope(doc: Mapping[str, object], build_dir: str | None) -> list[str]:
    errs: list[str] = []

    if doc.get("schema_version") != "fact-pack-envelope-v1":
        errs.append(f"E-envelope-schema-version: expected 'fact-pack-envelope-v1', "
                    f"got {doc.get('schema_version')!r}")

    facts_path = doc.get("facts_path")
    if not isinstance(facts_path, str) or not facts_path.endswith("facts.md"):
        errs.append(f"E-envelope-facts-path: {facts_path!r} must be a path ending in facts.md")
    elif build_dir is not None:
        # Shape check above only requires *a* path ending in facts.md; with a
        # --build-dir available, pin it down exactly — the envelope must
        # declare the facts.md that actually lives in the directory it was
        # staged under, not an ambiguously-similar path (spec §4 layout).
        expected_facts_path = os.path.normpath(os.path.join(build_dir, "facts.md"))
        if os.path.normpath(facts_path) != expected_facts_path:
            errs.append(f"E-envelope-facts-path-mismatch: {facts_path!r} does not resolve "
                        f"to {expected_facts_path!r} under build_dir {build_dir!r}")

    registry = doc.get("registry")
    if not isinstance(registry, dict):
        errs.append(f"E-envelope-registry: 'registry' missing or not an object, got {registry!r}")
        registry = {}

    if registry.get("schema_version") != "fact-pack-sources-v1":
        errs.append(f"E-envelope-registry-schema-version: expected 'fact-pack-sources-v1', "
                    f"got {registry.get('schema_version')!r}")

    registry_slug = registry.get("slug")
    if not isinstance(registry_slug, str) or not registry_slug:
        errs.append("E-envelope-registry-slug: missing non-empty 'slug'")
    elif build_dir is not None:
        # Production build dirs are always `.automaton/research/<slug>/`
        # (enforced on the manifest side by E-manifest-build-dir); pin the
        # registry's own declared slug to the directory it actually landed
        # in, catching e.g. a registry copy-pasted from a different run.
        expected_slug = os.path.basename(os.path.normpath(build_dir))
        if registry_slug != expected_slug:
            errs.append(f"E-envelope-registry-slug-mismatch: registry slug {registry_slug!r} "
                        f"does not match build_dir basename {expected_slug!r}")

    facts_digest = registry.get("facts_digest")
    digest_ok = isinstance(facts_digest, str) and re.match(r"^sha256:[0-9a-f]{64}$", facts_digest)
    if not digest_ok:
        errs.append(f"E-envelope-digest-format: {facts_digest!r} must match 'sha256:<64 hex chars>'")

    sources = registry.get("sources")
    if not isinstance(sources, list):
        errs.append(f"E-envelope-sources: 'sources' missing or not a list, got {sources!r}")
        sources = []

    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            errs.append(f"E-envelope-source-entry: sources[{i}] is not an object")
            continue
        sid = s.get("id")
        if not isinstance(sid, str) or not _FP_ID_RE.match(sid):
            errs.append(f"E-envelope-source-id: {sid!r} does not match ^FP[1-9][0-9]*$")

        url = s.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            errs.append(f"E-envelope-source-url: {url!r} (source {sid!r}) must start with https://")

        if not isinstance(s.get("title"), str) or not s.get("title"):
            errs.append(f"E-envelope-source-title: source {sid!r} missing non-empty 'title'")

        if not isinstance(s.get("publisher"), str) or not s.get("publisher"):
            errs.append(f"E-envelope-source-publisher: source {sid!r} missing non-empty 'publisher'")

        accessed_at = s.get("accessed_at")
        if not isinstance(accessed_at, str) or not _DATE_RE.match(accessed_at):
            errs.append(f"E-envelope-source-date: {accessed_at!r} (source {sid!r}) is not YYYY-MM-DD")

        status = s.get("status")
        if status not in _STATUS_VALUES:
            errs.append(f"E-envelope-source-status: {status!r} (source {sid!r}) not in {_STATUS_VALUES}")

    sids = [s.get("id") for s in sources if isinstance(s, dict)]
    seen, dupes = set(), []
    for sid in sids:
        if not isinstance(sid, str):
            # Non-string ids are already flagged as E-envelope-source-id above;
            # skip here so the set membership check below never hashes one.
            continue
        if sid in seen and sid not in dupes:
            dupes.append(sid)
        seen.add(sid)
    if dupes:
        errs.append(f"E-envelope-source-duplicate: {dupes}")

    if build_dir is not None and digest_ok:
        facts_file = Path(build_dir) / "facts.md"
        try:
            actual = sha256_file(facts_file)
        except OSError as e:
            errs.append(f"E-envelope-facts-missing: {facts_file}: {e}")
        else:
            if actual != facts_digest:
                errs.append(f"E-envelope-digest-mismatch: expected {facts_digest}, "
                            f"computed {actual} from {facts_file}")

    return errs
