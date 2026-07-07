"""
Query the knowledge base using index-guided retrieval (no RAG).

The LLM reads the index, picks relevant articles, and synthesizes an answer.
No vector database, no embeddings, no chunking - just structured markdown
and an index the LLM can reason over.

Usage:
    uv run python query.py "How should I handle auth redirects?"
    uv run python query.py "What patterns do I use for API design?" --save
"""

from __future__ import annotations

import argparse
import sys

from scripts.core.agent import QUERY_FILEBACK_OPTIONS, QUERY_OPTIONS, run_agent
from scripts.core.cli import CliContextP, cli_main
from scripts.core.config import Config, now_iso
from scripts.core.constants import MARKDOWN_GLOB, QA_SUBDIR
from scripts.core.errors import AgentError, WikiError
from scripts.core.exit_codes import ExitCode
from scripts.core.render import load_schemas
from scripts.core.utils import load_state, read_all_wiki_content, save_state
from scripts.prompts import build_query


async def run_query(config: Config, question: str, *, file_back: bool = False) -> str:
    """Query the knowledge base and optionally file the answer back."""
    cfg = config
    wiki_content = read_all_wiki_content(cfg)

    qa_template = None
    timestamp = None
    wiki_dir_arg = None
    knowledge_dir_arg = None
    if file_back:
        qa_template = load_schemas(cfg.wiki)[QA_SUBDIR].article_template
        timestamp = now_iso()
        wiki_dir_arg = cfg.wiki
        knowledge_dir_arg = cfg.wiki
    prompt = build_query(
        question=question,
        wiki_content=wiki_content,
        file_back=file_back,
        qa_template=qa_template,
        timestamp=timestamp,
        wiki_dir=wiki_dir_arg,
        knowledge_dir=knowledge_dir_arg,
    )

    options = QUERY_FILEBACK_OPTIONS if file_back else QUERY_OPTIONS
    answer = ""
    cost = 0.0
    try:
        result = await run_agent(prompt, cwd=cfg.root, options=options)
        answer = result.text
        cost = result.cost_usd
    except Exception as e:
        # State intentionally not updated on failure — failed queries
        # should not inflate query_count or total_cost in wiki/state.json.
        raise AgentError(stage="query-run", underlying=str(e)) from e

    # Update state only on successful run
    state = load_state(cfg)
    state["query_count"] = state.get("query_count", 0) + 1
    state["total_cost"] = state.get("total_cost", 0.0) + cost
    save_state(cfg, state)

    return answer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query the knowledge base")
    parser.add_argument("question", help="The question to ask")
    parser.add_argument(
        "--save",
        action="store_true",
        help="File the answer back into the knowledge base as a Q&A article",
    )
    return parser


async def _run_query_cli(config: Config, args: argparse.Namespace) -> None:
    print(f"Question: {args.question}")
    print(f"File back: {'yes' if args.save else 'no'}")
    print("-" * 60)

    answer = await run_query(config, args.question, file_back=args.save)
    print(answer)

    if args.save:
        print("\n" + "-" * 60)
        qa_dir = config.wiki / QA_SUBDIR
        qa_count = len(list(qa_dir.glob(MARKDOWN_GLOB))) if qa_dir.exists() else 0
        print(f"Answer filed to wiki/qa/ ({qa_count} Q&A articles total)")


@cli_main(name="query", parser_factory=build_parser)
async def main(ctx: CliContextP) -> ExitCode:
    try:
        await _run_query_cli(ctx.config, ctx.args)
    except WikiError:
        raise  # Already-typed failures (e.g. AgentError from run_query) bubble as-is.
    except Exception as exc:
        raise AgentError(stage="query-run", underlying=str(exc)) from exc
    return ExitCode.OK


if __name__ == "__main__":
    sys.exit(main())
