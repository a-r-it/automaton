"""Canonicalize an opt-in model-routing.json for safe SessionStart injection.

The .automaton/development/model-routing.json file is project-local (git-ignored,
user-authored -- not repo-shared), and its contents are embedded into Claude's
SessionStart context by the session-start hook. Even for a local file, embedding
raw bytes would be a prompt-injection / secret-exfiltration vector if it were a
stray symlink or held junk, so this runs as defense-in-depth.

This module neutralizes that: parse the file as JSON, keep ONLY the known tier
keys whose values look like a model id, and re-emit a canonical object. Stray
prose, injection payloads, and secret-file contents are not the constrained
schema, so they collapse to {} (the hook then emits no routing notice). Size-
capped so a huge file can't stall the hook.

The routing schema:
    {"mechanical": "haiku", "standard": "sonnet", "frontier": "inherit"}
Values are model ids ("haiku", "claude-opus-4-8", "us.anthropic...") or the
literal "inherit" -- all match a conservative model-id charset.
"""
import json
import re
import sys

TIERS = ("mechanical", "standard", "frontier")
# Model ids / "inherit": start alnum, then alnum plus . : - up to 64 chars.
# Deliberately excludes quotes, spaces, <, >, {, }, and ALL control chars
# (incl. newline) -- the characters an injection payload needs to break out of
# the surrounding context tag. Matched with fullmatch() (NOT match() + "$",
# which would accept a trailing newline) so the no-control-char invariant holds.
VALUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
MAX_BYTES = 64 * 1024


def canonicalize(path):
    """Return a dict with only valid tier->model entries; {} if anything is off."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_BYTES + 1)
    except OSError:
        return {}
    if len(raw) > MAX_BYTES:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for tier in TIERS:
        v = data.get(tier)
        if isinstance(v, str) and VALUE_RE.fullmatch(v):
            out[tier] = v
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("{}")
        sys.exit(0)
    print(json.dumps(canonicalize(sys.argv[1]), separators=(",", ":")))
