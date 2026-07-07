from __future__ import annotations

_TEMPLATE = (
    "Write a single-line git commit subject (max 72 chars) summarising the "
    "changes in this diff. Use imperative mood, no trailing period, no type "
    "prefix (the 'docs(wiki):' prefix is added automatically). Return ONLY "
    "the subject line, nothing else.\n\n"
    "## Diff\n\n"
    "{diff}"
)


def build(diff: str) -> str:
    return _TEMPLATE.format(diff=diff)
