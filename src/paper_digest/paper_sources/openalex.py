"""OpenAlex source placeholder."""

from __future__ import annotations

from paper_digest.exceptions import SourceLookupError
from paper_digest.models import PaperMetadata


class OpenAlexSource:
    """Reserved extension point for OpenAlex support."""

    name = "openalex"

    def matches_url(self, url: str) -> bool:
        return "openalex.org" in url

    def get_by_url(self, url: str) -> PaperMetadata:
        raise SourceLookupError("OpenAlex support is not implemented in this MVP.")

    def search_by_title(self, title: str, limit: int = 5) -> list[PaperMetadata]:
        return []

    def search_by_topic(self, topic: str, limit: int = 10) -> list[PaperMetadata]:
        return []
