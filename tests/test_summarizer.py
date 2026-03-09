from paper_digest.models import PaperMetadata, PaperSection, ParsedPaper
from paper_digest.summarizer.heuristic import HeuristicSummarizer


def test_heuristic_summarizer_marks_summary_basis() -> None:
    metadata = PaperMetadata(
        source="arxiv",
        source_id="2501.01234",
        arxiv_id="2501.01234",
        title="RAG with Better Retrieval",
        authors=["Alice"],
        abstract=(
            "We propose a retrieval-augmented generation pipeline that improves answer "
            "grounding."
        ),
        year=2025,
        pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
        abs_url="https://arxiv.org/abs/2501.01234",
        categories=["cs.CL"],
    )
    parsed = ParsedPaper(
        metadata=metadata,
        text="",
        abstract_text=metadata.abstract,
        sections=[
            PaperSection(
                heading="Introduction",
                body="This paper studies retrieval noise and hallucination in RAG systems.",
                order=1,
            )
        ],
        warnings=["pdf parsing fallback"],
    )

    summary = HeuristicSummarizer().summarize_paper(parsed)

    assert summary.summary_basis == "仅基于摘要生成"
    assert "检索增强生成" in summary.one_sentence or "检索增强生成" in summary.research_context
    assert summary.method_breakdown
    assert summary.follow_up_advice
