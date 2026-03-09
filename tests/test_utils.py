from paper_digest.utils import extract_arxiv_id, slugify


def test_slugify_is_stable_and_readable() -> None:
    assert slugify("Attention Is All You Need") == "attention-is-all-you-need"
    assert slugify("RAG: Retrieval + Generation / 2025") == "rag-retrieval-generation-2025"
    assert slugify("自动驾驶 DETR 阅读") == "自动驾驶-detr-阅读"


def test_extract_arxiv_id_from_abs_url() -> None:
    assert extract_arxiv_id("https://arxiv.org/abs/2501.01234v2") == "2501.01234v2"
