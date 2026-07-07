"""CLI entry for `mnemic:wiki render-prompt`."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from scripts.core.cli import CliContextP, cli_main
from scripts.core.constants import (
    LIBRARIAN_DIR,
    MARKDOWN_GLOB,
    SCHEMA_FILENAME,
    SCHEMAS_DIR,
)
from scripts.core.exit_codes import ExitCode
from scripts.core.render import load_schemas, render_prompt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the compile prompt exactly as sent to the compile agent.",
    )
    parser.add_argument(
        "--plugin-defaults",
        action="store_true",
        help="Render from plugin-shipped templates rather than the active wiki.",
    )
    return parser


@cli_main(name="render-prompt", parser_factory=_build_parser)
def main(ctx: CliContextP) -> ExitCode:
    """Render the compile prompt and write it to stdout.

    Args:
        ctx: CLI context with parsed args and loaded config.

    Returns:
        ExitCode.OK on success.
    """
    cfg = ctx.config
    if ctx.args.plugin_defaults:
        tmp_wiki = _plugin_schemas_as_wiki(cfg.compiler_root)
        registry = load_schemas(tmp_wiki)
    else:
        registry = load_schemas(cfg.wiki)

    static_md = cfg.static_prompt_file.read_text(encoding="utf-8")
    out = render_prompt(
        registry,
        static_md,
        wiki=cfg.wiki_subdir,
        daily=cfg.daily_subdir,
        sources=cfg.sources_subdir,
    )
    sys.stdout.write(out)
    return ExitCode.OK


def _plugin_schemas_as_wiki(compiler_root: Path) -> Path:
    """Materialize plugin schemas into a temp dir shaped like a user wiki.

    Returns:
        Path to the temporary directory containing materialised schema files.
    """
    tmp = Path(tempfile.mkdtemp(prefix="librarian-defaults-"))
    plugin = compiler_root / LIBRARIAN_DIR / SCHEMAS_DIR
    for plugin_file in sorted(plugin.glob(MARKDOWN_GLOB)):
        text = plugin_file.read_text(encoding="utf-8")
        default_dir = next(
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("default_dir:")
        )
        target = tmp / default_dir / SCHEMA_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp


if __name__ == "__main__":
    sys.exit(main())
