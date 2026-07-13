"""scope kind + scope_digest canonicalization (hook-free redesign §3)."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping

from business_research.validation.manifest import _SLUG_RE

_DECISION_TYPES = ("explore", "compare", "go-no-go", "launch")
_DIGEST_FIELDS = ("market_definition", "geography", "horizon",
                  "decision_question", "decision_type")


def scope_digest(doc: Mapping[str, object]) -> str:
    canonical = {k: doc.get(k) for k in _DIGEST_FIELDS}
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(unicodedata.normalize("NFC", blob).encode("utf-8")).hexdigest()


def validate_scope(doc: object) -> list[str]:
    if not isinstance(doc, dict):
        return [f"E-scope-doc-type: scope must be a single JSON object, got {type(doc).__name__}"]
    errs: list[str] = []
    if doc.get("schema_version") != "business-scope-v1":
        errs.append(f"E-scope-schema-version: expected 'business-scope-v1', "
                    f"got {doc.get('schema_version')!r}")
    if doc.get("decision_type") not in _DECISION_TYPES:
        errs.append(f"E-scope-decision-type: {doc.get('decision_type')!r} not in {_DECISION_TYPES}")
    slug = doc.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        errs.append(f"E-scope-slug: {slug!r} does not match ^[a-z0-9]+(-[a-z0-9]+)*$")
    for k in ("market_definition", "geography", "horizon", "decision_question"):
        if not isinstance(doc.get(k), str) or not doc.get(k):
            errs.append(f"E-scope-{k.replace('_', '-')}: missing non-empty {k!r}")
    angles = doc.get("lens_angles")
    if not isinstance(angles, dict) or not all(
        isinstance(x, str) and isinstance(y, str) for x, y in angles.items()
    ):
        errs.append("E-scope-lens-angles: 'lens_angles' must be a map of agent_id->angle strings")
    if not isinstance(doc.get("scope_defaults_used"), bool):
        errs.append("E-scope-defaults-flag: 'scope_defaults_used' must be a bool")
    if not isinstance(doc.get("defaulted_fields"), list):
        errs.append("E-scope-defaulted-fields: 'defaulted_fields' must be a list")
    return errs


def validate_manifest_scope_link(manifest_doc: Mapping[str, object], scope_doc: object) -> list[str]:
    """Build-dir/scope-aware cross-check, deliberately kept OUT of
    `validate_manifest` (doc-only — research/verification/survival load just
    the manifest and call it with no scope available). Only invoked where
    the actual scope.json is on hand (CLI `manifest --scope <path>`).

    Closes the loop `validate_manifest`'s doc-only shape check cannot: it
    recomputes `scope_digest(scope_doc)` from the real scope.json content
    and compares it to the manifest's stamped `scope_digest`, so a forged or
    stale digest (scope.json edited after stamping, or an arbitrary
    valid-hex string typed into the manifest) is caught instead of silently
    matching every other copy of the same digest.
    """
    errs = validate_scope(scope_doc)
    if errs or not isinstance(scope_doc, dict):
        return errs

    link_errs: list[str] = []
    computed = scope_digest(scope_doc)
    stamped = manifest_doc.get("scope_digest")
    if computed != stamped:
        link_errs.append(
            f"E-manifest-scope-digest-mismatch: manifest scope_digest {stamped!r} "
            f"does not match scope_digest(scope.json) {computed!r}"
        )

    manifest_slug = manifest_doc.get("slug")
    scope_slug = scope_doc.get("slug")
    if manifest_slug != scope_slug:
        link_errs.append(
            f"E-manifest-scope-slug-mismatch: manifest slug {manifest_slug!r} "
            f"!= scope slug {scope_slug!r}"
        )
    return link_errs
