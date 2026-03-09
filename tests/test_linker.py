from pathlib import Path

from paper_digest.knowledge.linker import MarkdownAutoLinker
from paper_digest.models import NoteIndex, NoteIndexEntry


def test_markdown_auto_linker_only_links_plain_body_text() -> None:
    linker = MarkdownAutoLinker()
    note_index = NoteIndex(
        notes=[
            NoteIndexEntry(
                path="文献库/检索增强生成/index.md",
                absolute_path=Path("/tmp/文献库/检索增强生成/index.md"),
                title="检索增强生成专题",
            ),
            NoteIndexEntry(
                path="概念/自动驾驶.md",
                absolute_path=Path("/tmp/概念/自动驾驶.md"),
                title="自动驾驶",
            ),
        ],
        keyword_to_notes={
            "rag": ["文献库/检索增强生成/index.md"],
            "自动驾驶": ["概念/自动驾驶.md"],
        },
    )
    content = """---
title: RAG summary
---
# RAG heading
This RAG system is relevant for 自动驾驶.

```text
RAG in code blocks should stay untouched.
```

Already linked [[文献库/检索增强生成/index|RAG]]
[external](https://example.com)
"""

    linked = linker.link(content=content, note_index=note_index)

    assert "# RAG heading" in linked
    assert "[[文献库/检索增强生成/index|RAG]] system" in linked
    assert "[[概念/自动驾驶|自动驾驶]]" in linked
    assert "RAG in code blocks should stay untouched." in linked
    assert "Already linked [[文献库/检索增强生成/index|RAG]]" in linked
    assert "[external](https://example.com)" in linked
