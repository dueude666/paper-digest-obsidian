from pathlib import Path

from paper_digest.config import AppSettings
from paper_digest.paper_sources.arxiv import ArxivSource, _normalize_pdf_url


class FakeHttpClient:
    def __init__(self, xml_text: str):
        self.xml_text = xml_text

    def get_text(self, url: str, *, params=None, headers=None) -> str:
        return self.xml_text

    def get_bytes(self, url: str, *, params=None, headers=None) -> bytes:
        raise NotImplementedError

    def post_json(self, url: str, *, json_body, headers=None):
        raise NotImplementedError


def test_arxiv_source_parses_atom_feed() -> None:
    xml_text = Path("tests/fixtures/arxiv_feed.xml").read_text(encoding="utf-8")
    source = ArxivSource(http_client=FakeHttpClient(xml_text), settings=AppSettings())

    results = source.search_by_title("Attention Is All You Need", limit=1)

    assert len(results) == 1
    paper = results[0]
    assert paper.title == "Attention Is All You Need"
    assert paper.arxiv_id == "1706.03762v7"
    assert paper.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert paper.pdf_url == "http://arxiv.org/pdf/1706.03762v7.pdf"
    assert paper.year == 2017


def test_arxiv_pdf_url_is_normalized() -> None:
    assert _normalize_pdf_url("https://arxiv.org/pdf/2511.09347v2") == (
        "https://arxiv.org/pdf/2511.09347v2.pdf"
    )
    assert _normalize_pdf_url("https://arxiv.org/pdf/2110.06922v1.pdf") == (
        "https://arxiv.org/pdf/2110.06922v1.pdf"
    )
