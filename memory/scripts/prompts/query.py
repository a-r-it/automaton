from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.core.constants import QA_SUBDIR

if TYPE_CHECKING:
    from pathlib import Path

_BASE = """You are a knowledge base query engine. Answer the user's question by
consulting the knowledge base below.

## How to Answer

1. Read the INDEX section first - it lists every article with a one-line summary
2. Identify 3-10 articles that are relevant to the question
3. Read those articles carefully (they're included below)
4. Synthesize a clear, thorough answer
5. Cite your sources using [[wikilinks]] (e.g., [[concepts/supabase-auth]])
6. If the knowledge base doesn't contain relevant information, say so honestly

## Knowledge Base

{wiki_content}

## Question

{question}
{file_back_section}"""

_FILE_BACK = """

## File Back Instructions

After answering, save the answer as a Q&A article:

1. Create `{qa_dir}/<slug>.md` where slug is a lowercase-hyphenated version of the question.
   Follow the qa schema template exactly:

```markdown
{qa_template}```

   Use today's date ({date}) for `created:`, `updated:`, and `filed:`. Fill `consulted:` with the `[[wikilinks]]` of articles you read while answering.

2. Update `{qa_dir}/index.md` (sub-index):
   - Add a row: `| [[qa/<slug>]] | <one-line summary> | qa | {date} |`
   - If `qa/index.md` does not exist, create it with the header row first:
     ```
     # qa/ Index
     | Article | Summary | Tags | Updated |
     |---------|---------|------|---------|
     ```

3. Update `{knowledge_index}` (global index):
   - Find or create a `## qa/` section.
   - Add or update the article's row in that section.

4. Append to `{knowledge_log}`:
   ```
   ## [{timestamp}] query (filed) | <question summary>
   - Question: {question}
   - Consulted: [[list of articles read]]
   - Filed to: [[qa/<slug>]]
   ```
"""


def build(
    question: str,
    wiki_content: str,
    *,
    file_back: bool = False,
    qa_template: str | None = None,
    timestamp: str | None = None,
    wiki_dir: Path | None = None,
    knowledge_dir: Path | None = None,
) -> str:
    file_back_section = ""
    if file_back:
        if qa_template is None or timestamp is None or wiki_dir is None or knowledge_dir is None:
            raise ValueError(
                "file_back=True requires qa_template, timestamp, wiki_dir, knowledge_dir"
            )
        file_back_section = _FILE_BACK.format(
            qa_dir=wiki_dir / QA_SUBDIR,
            knowledge_index=knowledge_dir / "index.md",
            knowledge_log=knowledge_dir / "log.md",
            qa_template=qa_template,
            timestamp=timestamp,
            date=timestamp[:10],
            question=question,
        )
    return _BASE.format(
        question=question,
        wiki_content=wiki_content,
        file_back_section=file_back_section,
    )
