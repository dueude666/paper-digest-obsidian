import json
from pathlib import Path

from paper_digest.config import AppSettings
from paper_digest.models import PaperMetadata, ParsedPaper
from paper_digest.summarizer.llm import OpenAICompatibleSummarizer


class FakeHttpClient:
    def __init__(self, content: str):
        self._content = content

    def post_json(self, url: str, *, json_body, headers=None):  # noqa: ANN001
        return {
            "choices": [
                {
                    "message": {
                        "content": self._content,
                    }
                }
            ]
        }


def build_parsed_paper() -> ParsedPaper:
    metadata = PaperMetadata(
        source="arxiv",
        source_id="2501.01234",
        arxiv_id="2501.01234",
        title="A Strong RAG Paper",
        authors=["Alice", "Bob"],
        abstract="This paper studies retrieval noise and answer grounding in RAG.",
        year=2025,
        pdf_url="https://arxiv.org/pdf/2501.01234.pdf",
        abs_url="https://arxiv.org/abs/2501.01234",
        categories=["cs.CL"],
    )
    return ParsedPaper(
        metadata=metadata,
        pdf_path=Path("dummy.pdf"),
        text="We propose a retrieval pipeline with query rewrite and answer validation.",
        abstract_text=metadata.abstract,
        warnings=[],
    )


def test_openai_compatible_summarizer_overlays_beginner_friendly_fields() -> None:
    parsed_paper = build_parsed_paper()
    settings = AppSettings(
        summary_backend="openai-compatible",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-5.2",
        summary_audience="beginner",
        summary_detail_level="detailed",
    )
    payload = json.dumps(
        {
            "one_sentence": (
                "这篇论文可以理解成先找资料，再回答问题，" "并重点修复 RAG 容易找错资料的缺点。"
            ),
            "core_method": (
                "模型不是只做一次检索，而是把查询重写、结果过滤和答案校验串成一条完整流水线。"
            ),
            "datasets_or_benchmarks": "Natural Questions、HotpotQA",
            "main_results": "在给出的问答基准上，答案更稳定，幻觉更少。",
            "short_overview": [
                "它想解决 RAG 容易找错资料的问题。",
                "核心思路是把检索前、检索中、生成后的关键步骤都补强。",
                "实验在常见问答基准上完成。",
                "结果说明答案更稳，引用资料也更贴近问题。",
            ],
        },
        ensure_ascii=False,
    )
    summarizer = OpenAICompatibleSummarizer(
        settings=settings,
        http_client=FakeHttpClient(payload),
    )

    summary = summarizer.summarize_paper(parsed_paper)

    assert summary.one_sentence.startswith("这篇论文可以理解成先找资料")
    assert summary.core_method.startswith("模型不是只做一次检索")
    assert summary.datasets_or_benchmarks == "Natural Questions、HotpotQA"
    assert summary.main_results.startswith("在给出的问答基准上")
    assert len(summary.short_overview) == 4
