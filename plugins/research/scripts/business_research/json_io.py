"""Document loading and numeric constraints (V2 spec §5-§6)."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

__all__ = ["canonical_url", "load_document", "sha256_file"]

# Shared regex: YYYY-MM-DD dates (used by manifest and envelope validators)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# --- Number parsing (json.loads hooks) ---------------------------------------

_NUM_ERRORS: list[str] = []  # collected during json parse; reset per load_document call


def _parse_float(raw: str) -> float:
    """json.loads parse_float hook: fires for any token with a '.' or exponent."""
    low = raw.lower()
    if "e" in low:
        _NUM_ERRORS.append(f"E-num-exponent: {raw}")
    if raw.startswith("-") and float(raw) == 0.0:
        _NUM_ERRORS.append(f"E-num-negzero: {raw}")
    if "." in raw and len(raw.split(".", 1)[1]) > 4:
        _NUM_ERRORS.append(f"E-num-precision: {raw}")
    return float(raw)


def _parse_int(raw: str) -> int:
    """json.loads parse_int hook: fires only for bare-integer tokens (no '.'
    or exponent is lexically possible per the JSON number grammar), so the
    only check that applies is negative zero (raw "-0")."""
    if raw.startswith("-") and int(raw) == 0:
        _NUM_ERRORS.append(f"E-num-negzero: {raw}")
    return int(raw)


def _reject_const(name: str) -> int:
    """json.loads parse_constant hook: fires for NaN / Infinity / -Infinity."""
    _NUM_ERRORS.append(f"E-num-nonfinite: {name}")
    return 0


def load_document(path: str | Path) -> tuple[Any, list[str]]:
    """Strict JSON load enforcing spec §5's numeric-value rules (exponent
    notation, >4 decimal places, negative zero, NaN/Infinity all rejected).
    Returns (doc, errors); doc is None only on I/O or JSON-syntax failure —
    numeric-rule violations are reported alongside a still-parsed doc.

    `doc` is `Any`, not a narrower JSON-value union: this is the raw
    `json.loads` boundary (its own stub returns `Any`) and every caller
    downstream immediately `isinstance`-narrows before use — see
    business_research.models module docstring, "validators ... work on raw
    dicts and must not assume this shape."""
    global _NUM_ERRORS
    _NUM_ERRORS = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return None, [f"E-io-read: {path}: {e}"]
    try:
        doc = json.loads(text, parse_float=_parse_float, parse_int=_parse_int,
                          parse_constant=_reject_const)
    except json.JSONDecodeError as e:
        return None, [f"E-json-parse: {path}: {e}"]
    return doc, list(_NUM_ERRORS)


# --- URL canonicalization -----------------------------------------------------

def canonical_url(url: str) -> str:
    """Lowercase scheme/host, drop trailing slash on path (default "/"),
    strip utm_* query params, sort remaining params, drop fragment."""
    p = urllib.parse.urlsplit(url.strip())
    query = "&".join(sorted(kv for kv in p.query.split("&")
                             if kv and not kv.lower().startswith("utm_")))
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


# --- File digest --------------------------------------------------------------

def sha256_file(path: str | Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
