from pathlib import Path

from paper_digest.knowledge.notes_index import NoteIndexService


def test_note_index_build_and_search(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers_dir = vault / "文献库" / "检索增强生成" / "论文笔记"
    assets_dir = vault / "文献库" / "检索增强生成" / "图片素材"
    papers_dir.mkdir(parents=True)
    assets_dir.mkdir(parents=True)

    (papers_dir / "rag-paper.md").write_text(
        """---
title: \"RAG: Retrieval Augmented Generation\"
authors:
  - Alice
tags:
  - rag
  - retrieval
  - 文献
arxiv_id: 2501.01234
---
This note summarizes a retrieval workflow.
""",
        encoding="utf-8",
    )
    (vault / "多模态推理.md").write_text(
        """---
title: Vision-Language Models
tags:
  - multimodal
---
Focus on image text reasoning.
""",
        encoding="utf-8",
    )
    (assets_dir / "ignore.md").write_text("# should not be indexed", encoding="utf-8")

    service = NoteIndexService()
    note_index = service.build(vault_root=vault, include_root=vault)

    assert len(note_index.notes) == 2
    assert "rag" in note_index.keyword_to_notes
    assert "文献" not in note_index.keyword_to_notes
    assert note_index.keyword_to_notes["rag"] == ["文献库/检索增强生成/论文笔记/rag-paper.md"]

    results = service.search(note_index=note_index, query="retrieval rag", limit=5)

    assert len(results) == 1
    assert results[0].path == "文献库/检索增强生成/论文笔记/rag-paper.md"
    assert results[0].matched_terms == ["retrieval", "rag"]
