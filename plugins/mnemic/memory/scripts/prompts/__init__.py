"""Leaf package: pure prompt builders.

Each submodule exposes a single `build(...) -> str` function. Builders
must not import from sibling scripts, read the filesystem, or call
`datetime.now`. All runtime context is supplied by the caller.
"""

from __future__ import annotations

from .commit import build as build_commit
from .compile import build as build_compile
from .flush import build as build_flush
from .lint_semantic import build as build_lint_semantic
from .query import build as build_query

__all__ = [
    "build_commit",
    "build_compile",
    "build_flush",
    "build_lint_semantic",
    "build_query",
]
