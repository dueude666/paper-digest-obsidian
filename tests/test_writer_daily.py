from pathlib import Path

from paper_digest.config import AppSettings
from paper_digest.models import (
    DailyDigest,
    NoteIndex,
    NoteIndexEntry,
    PaperMetadata,
    PaperSummary,
    RecommendationScores,
    RecommendedPaper,
)
from paper_digest.obsidian_writer.writer import ObsidianWriter


def _build_metadata() -> PaperMetadata:
    return PaperMetadata(
        source="arxiv",
        source_id="2501.01234",
        arxiv_id="2501.01234",
        title="A Strong RAG Paper",
        authors=["Alice", "Bob"],
        abstract="This paper studies retrieval augmented generation for enterprise QA.",
        year=2025,
        pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
        abs_url="https://arxiv.org/abs/2501.01234",
        categories=["cs.CL"],
    )


def _build_summary() -> PaperSummary:
    metadata = _build_metadata()
    return PaperSummary(
        metadata=metadata,
        summary_basis="基于摘要和可提取正文生成",
        one_sentence="这是一篇面向企业知识问答的 RAG 方法论文。",
        research_context="论文聚焦企业知识问答中的检索增强生成。",
        research_problem="目标是降低检索噪声并提升答案一致性。",
        problem_evidence="This paper studies retrieval augmented generation for enterprise QA.",
        core_method="方法上结合查询重写、检索过滤和答案校验。",
        method_evidence="We combine query rewrite, retrieval filtering, and answer validation.",
        method_breakdown=["查询重写", "检索过滤", "答案校验"],
        experiment_setup=["在多个问答基准上评测。"],
        main_results="在多个基准上提升了准确率和稳定性。",
        results_evidence="The method improves answer grounding on multiple QA benchmarks.",
        key_findings=["相对基线有稳定提升。"],
        figure_reading_tips=["优先看方法总图。"],
        contributions=["给出一条完整的 RAG 流程。"],
        limitations=["需要额外检索开销。"],
        use_cases=["企业知识助手。"],
        follow_up_advice=["先看实验章节。"],
        reading_path=["先看方法总图。"],
        citation="Alice, Bob (2025). A Strong RAG Paper. arXiv:2501.01234.",
    )


def test_writer_auto_links_existing_notes_in_paper_body(tmp_path: Path) -> None:
    settings = AppSettings(obsidian_vault_path=tmp_path, auto_link_existing_notes=True)
    writer = ObsidianWriter(settings=settings)
    note_index = NoteIndex(
        notes=[
            NoteIndexEntry(
                path="概念/vector-database.md",
                absolute_path=tmp_path / "概念" / "vector-database.md",
                title="Vector Database",
                tag_keywords=["vector database"],
            )
        ],
        keyword_to_notes={"vector database": ["概念/vector-database.md"]},
    )
    summary = _build_summary().model_copy(
        update={
            "use_cases": ["Enterprise knowledge assistants with a vector database"],
        }
    )

    result = writer.write_paper(
        summary=summary, topic="检索增强生成", note_index=note_index, dry_run=False
    )

    content = result.path.read_text(encoding="utf-8")
    assert "[[概念/vector-database|vector database]]" in content


def test_writer_outputs_daily_digest_with_note_links(tmp_path: Path) -> None:
    settings = AppSettings(obsidian_vault_path=tmp_path)
    writer = ObsidianWriter(settings=settings)
    metadata = _build_metadata()
    digest = DailyDigest(
        date="2026-03-07",
        profile_name="research_interests",
        selection_rationale="混合近期 arXiv 论文和高影响论文。",
        overview="今天选出 1 篇推荐论文。",
        recommended_papers=[
            RecommendedPaper(
                metadata=metadata,
                scores=RecommendationScores(
                    relevance=4.0,
                    recency=3.0,
                    popularity=2.0,
                    quality=1.0,
                    recommendation=10.0,
                ),
                matched_domain="retrieval_augmented_generation",
                matched_keywords=["rag"],
                generated_note_path="文献库/检索增强生成/论文笔记/2025-2501-strong-rag-paper.md",
            )
        ],
    )

    result = writer.write_daily_digest(digest=digest, dry_run=False)

    assert result.written is True
    assert result.path.exists()
    content = result.path.read_text(encoding="utf-8")
    assert result.relative_path == "文献库/每日推荐/2026-03-07-论文推荐.md"
    assert (
        "[[文献库/检索增强生成/论文笔记/2025-2501-strong-rag-paper|A Strong RAG Paper]]" in content
    )
