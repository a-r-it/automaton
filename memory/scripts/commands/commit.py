"""Auto-commit wiki/ and daily/ updates after compile.py runs.

Awaited from compile.py's async main() tail. A single haiku LLM call
produces the commit subject line from the diff; Python handles all git
operations with a hard-coded pathspec. Never raises — all outcomes are
logged to the shared flush.log via the root logger.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.core.agent import COMMIT_OPTIONS, run_agent
from scripts.prompts import build_commit

if TYPE_CHECKING:
    from scripts.core.config import Config

log = logging.getLogger(__name__)

MAX_SUBJECT_LEN = 72
MAX_DIFF_CHARS = 8000
COMMIT_PREFIX = "docs(wiki): "
CO_AUTHOR = "Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"


def _validate_subject(raw: str) -> str | None:
    if not raw:
        return None
    first_line = raw.strip().split("\n", 1)[0].strip()
    if not first_line:
        return None
    if len(first_line) > MAX_SUBJECT_LEN:
        first_line = first_line[: MAX_SUBJECT_LEN - 3] + "..."
    return first_line


async def run(config: Config) -> None:
    """Auto-commit wiki/ and daily/ changes. Never raises."""
    try:
        await _run(config)
    except Exception as e:
        log.exception("[commit] ERROR: unexpected: %s", type(e).__name__)


def _reset_staged(root: Path, existing: list[str]) -> None:
    """Unstage paths we just staged so failure leaves the index untouched."""
    subprocess.run(
        ["git", "reset", "HEAD", "--", *existing],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


async def _run(config: Config) -> None:
    cfg = config
    root = cfg.root
    if not _in_git_repo(root):
        log.info("[commit] SKIP: not a git repo")
        return
    if not _no_merge_in_progress(root):
        log.info("[commit] SKIP: merge/rebase in progress")
        return

    scope_dirs = (cfg.wiki_subdir, cfg.daily_subdir)
    scope = _active_scope(root, scope_dirs)
    if not scope:
        log.info("[commit] SKIP: no scope changes")
        return

    tracked, untracked = _files_to_stage(root, scope)
    try:
        if tracked:
            subprocess.run(  # noqa: ASYNC221  # CLI tool; blocking git I/O is negligible vs. LLM call
                ["git", "add", "-u", "--", *tracked],
                cwd=root,
                capture_output=True,
                check=True,
                text=True,
            )
        if untracked:
            subprocess.run(  # noqa: ASYNC221  # CLI tool; blocking git I/O is negligible vs. LLM call
                ["git", "add", "--", *untracked],
                cwd=root,
                capture_output=True,
                check=True,
                text=True,
            )
    except subprocess.CalledProcessError as e:
        log.exception("[commit] ERROR: git add failed: %s", (e.stderr or "").strip())
        return

    diff = _collect_diff(root, scope)
    try:
        raw = await _generate_subject(root, diff)
    except Exception as e:
        log.exception("[commit] ERROR: LLM failed: %s", type(e).__name__)
        _reset_staged(root, scope)
        return

    subject = _validate_subject(raw)
    if subject is None:
        log.info("[commit] SKIP: invalid LLM subject: %r", raw)
        _reset_staged(root, scope)
        return

    _commit(root, subject, scope)


def _collect_diff(root: Path, scope: list[str]) -> str:
    result = subprocess.run(
        ["git", "diff", "--cached", "HEAD", "--", *scope],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n...[truncated]"
    return diff


async def _generate_subject(root: Path, diff: str) -> str:
    prompt = build_commit(diff=diff)
    result = await run_agent(prompt, cwd=root, options=COMMIT_OPTIONS)
    return result.text


def _commit(root: Path, subject: str, scope: list[str]) -> None:
    msg = f"{COMMIT_PREFIX}{subject}\n\n{CO_AUTHOR}"
    try:
        subprocess.run(
            ["git", "commit", "-m", msg, "--", *scope],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
        )
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        log.info("[commit] committed %s: %s", sha, subject)
    except subprocess.CalledProcessError as e:
        log.exception("[commit] ERROR: git failed: %s", (e.stderr or "").strip())
        _reset_staged(root, scope)


def _active_scope(root: Path, scope_dirs: tuple[str, ...]) -> list[str]:
    """Scope dirs that exist on disk AND have non-ignored changes.

    `git status --porcelain -- <d>` omits ignored files by default, so a fully
    gitignored dir returns empty and is dropped. Non-empty means at least one
    tracked-or-unignored path inside — commit/reset pathspecs are safe to use.
    Staging itself goes through individual file paths from `_files_to_stage`
    because `git add -- <dir>` still fatals when the dir itself matches an
    ignore rule, even when tracked files live inside.
    """
    active = []
    for d in scope_dirs:
        if not (root / d).exists():
            continue
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", d],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            active.append(d)
    return active


def _files_to_stage(root: Path, scope: list[str]) -> tuple[list[str], list[str]]:
    """Return (tracked, untracked) file lists to stage under scope dirs.

    Tracked paths go through `git add -u`, which updates the index without
    complaining about gitignored parents — staging a tracked file inside an
    ignored dir is the only way auto-commit can coexist with the user ignoring
    `daily/` or `wiki/`. Untracked paths come from `ls-files --others
    --exclude-standard`, so they're already filtered against ignore rules and
    a plain `git add` is safe.
    """
    tracked: set[str] = set()
    untracked: set[str] = set()
    for d in scope:
        for args, sink in (
            (["--modified"], tracked),
            (["--deleted"], tracked),
            (["--others", "--exclude-standard"], untracked),
        ):
            result = subprocess.run(
                ["git", "ls-files", "-z", *args, "--", d],
                cwd=root,
                capture_output=True,
                check=True,
                text=True,
            )
            sink.update(p for p in result.stdout.split("\0") if p)
    return sorted(tracked), sorted(untracked)


def _in_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def _no_merge_in_progress(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return True  # not a git repo — _in_git_repo() handles that separately
    git_dir = Path(result.stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        return False
    return not any(git_dir.glob("rebase-*"))
