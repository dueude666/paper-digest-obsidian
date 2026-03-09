from pathlib import Path

from paper_digest.config import AppSettings
from paper_digest.models import PaperMetadata, PaperSection, PaperSummary, ParsedPaper, TopicSummary
from paper_digest.obsidian_writer.writer import ObsidianWriter


def build_summary() -> PaperSummary:
    metadata = PaperMetadata(
        source="arxiv",
        source_id="2501.01234",
        arxiv_id="2501.01234",
        title="A Strong RAG Paper",
        authors=["Alice", "Bob"],
        abstract="This paper studies RAG.",
        year=2025,
        pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
        abs_url="https://arxiv.org/abs/2501.01234",
        categories=["cs.CL"],
    )
    return PaperSummary(
        metadata=metadata,
        summary_basis="基于摘要和部分正文生成",
        one_sentence="这篇论文提出了一种更稳定的 RAG 框架。",
        research_context="论文背景是知识密集型问答中的检索噪声问题。",
        research_problem="作者重点解决检索噪声和答案一致性不足的问题。",
        problem_evidence="This paper studies retrieval noise and hallucination in RAG systems.",
        core_method="方法把查询重写、检索过滤和答案校验串成统一流程。",
        method_evidence="We propose a retrieval pipeline with query rewrite and answer validation.",
        method_breakdown=["先重写查询。", "再过滤检索结果。", "最后做答案校验。"],
        experiment_setup=["在多个问答基准上评测。", "重点关注准确率和稳定性。"],
        main_results="在多个问答基准上取得了更稳定的结果。",
        results_evidence="The method improves answer grounding on multiple QA benchmarks.",
        key_findings=["相对基线有稳定提升。", "更适合企业知识库问答。"],
        figure_reading_tips=["先看方法总图，再看主结果表。"],
        contributions=["提出新的 RAG 流程", "给出详细实验对比"],
        limitations=["依赖额外检索成本"],
        use_cases=["企业知识库问答"],
        follow_up_advice=["优先阅读实验章节"],
        reading_path=["先看方法总图", "再看主结果表"],
        citation="Alice, Bob (2025). A Strong RAG Paper. arXiv:2501.01234.",
        short_overview=["一句话总结", "研究问题", "核心方法", "实验结果"],
        problem_definition="检索噪声和答案一致性问题",
        method_category="检索增强方法",
        datasets_or_benchmarks="Natural Questions、HotpotQA",
        strengths=["结果稳定"],
        weaknesses=["成本增加"],
        paper_role="core method",
    )


def build_parsed_paper() -> ParsedPaper:
    metadata = build_summary().metadata
    return ParsedPaper(
        metadata=metadata,
        text="Introduction\nThis is the intro.\n\nMethod\nThis is the method section.",
        abstract_text="This paper studies RAG in detail.",
        sections=[
            PaperSection(heading="Introduction", body="This is the intro.", order=0),
            PaperSection(heading="Method", body="This is the method section.", order=1),
        ],
        references_text="[1] Reference entry.",
        extraction_method="pymupdf",
    )


def test_writer_outputs_obsidian_markdown(tmp_path: Path) -> None:
    settings = AppSettings(obsidian_vault_path=tmp_path)
    writer = ObsidianWriter(settings=settings)
    summary = build_summary()

    result = writer.write_paper(summary=summary, topic="检索增强生成", dry_run=False)

    assert result.written is True
    assert result.path.exists()
    assert result.relative_path.startswith("文献库/")
    content = result.path.read_text(encoding="utf-8")
    assert "title: A Strong RAG Paper" in content
    assert "## 先讲人话" in content
    assert "小白先看这 5 行" in content
    assert "## 核心方法解读" in content
    assert "## 重点图示与看图建议" in content
    assert "企业知识库问答" in content


def test_writer_outputs_topic_index(tmp_path: Path) -> None:
    settings = AppSettings(obsidian_vault_path=tmp_path)
    writer = ObsidianWriter(settings=settings)
    summary = build_summary()
    paper_result = writer.write_paper(summary=summary, topic="检索增强生成", dry_run=False)
    topic_summary = TopicSummary(
        topic="检索增强生成",
        query="arXiv query='rag', limit=1",
        limit=1,
        selection_rationale="优先选择主题直接相关的论文。",
        why_these_papers="覆盖该方向的核心方法。",
        overview="这是一个 RAG 专题索引。",
        papers=[summary],
        reading_order=["1. 先读 A Strong RAG Paper"],
    )

    result = writer.write_topic_index(
        topic_summary=topic_summary,
        note_results=[paper_result],
        topic="检索增强生成",
        dry_run=False,
    )

    assert result.path.exists()
    content = result.path.read_text(encoding="utf-8")
    assert "# 检索增强生成 专题索引" in content
    assert "[[论文笔记/" in content


def test_writer_outputs_full_paper_note_and_syncs_pdf(tmp_path: Path) -> None:
    settings = AppSettings(obsidian_vault_path=tmp_path)
    writer = ObsidianWriter(settings=settings)
    parsed_paper = build_parsed_paper()
    pdf_source = tmp_path / "source.pdf"
    pdf_source.write_bytes(b"%PDF-1.4 test pdf")

    result = writer.write_full_paper(
        parsed_paper=parsed_paper,
        topic="检索增强生成",
        pdf_source_path=pdf_source,
        dry_run=False,
    )

    assert result.written is True
    assert result.path.exists()
    assert "论文全文" in result.relative_path
    content = result.path.read_text(encoding="utf-8")
    assert "# A Strong RAG Paper 全文查看" in content
    assert "## 原始 PDF" in content
    assert "![[../图片素材/" in content
    assert "## 正文提取" in content
    assert "### Introduction" in content
    synced_pdf = (
        tmp_path
        / "文献库"
        / "检索增强生成"
        / "图片素材"
        / writer.paper_slug_from_metadata(parsed_paper.metadata)
        / f"{writer.paper_slug_from_metadata(parsed_paper.metadata)}.pdf"
    )
    assert synced_pdf.exists()


def test_writer_outputs_source_pdf_for_direct_reading(tmp_path: Path) -> None:
    settings = AppSettings(obsidian_vault_path=tmp_path)
    writer = ObsidianWriter(settings=settings)
    metadata = build_summary().metadata
    pdf_source = tmp_path / "source-direct.pdf"
    pdf_source.write_bytes(b"%PDF-1.4 direct pdf")

    result = writer.write_source_pdf(
        metadata=metadata,
        topic="检索增强生成",
        pdf_source_path=pdf_source,
        dry_run=False,
    )

    assert result.written is True
    assert result.path.exists()
    assert result.relative_path.endswith(".pdf")
    assert "原文PDF" in result.relative_path
