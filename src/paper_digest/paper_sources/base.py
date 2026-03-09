"""Interfaces for paper metadata sources."""

from __future__ import annotations

from typing import Protocol

from paper_digest.models import PaperMetadata


class PaperSource(Protocol):
    """Source contract used by the fetcher layer."""

    name: str

    def matches_url(self, url: str) -> bool:
        """Return whether the source can resolve the provided URL."""

    def get_by_url(self, url: str) -> PaperMetadata:
        """Resolve a paper from a direct paper URL."""

    def search_by_title(self, title: str, limit: int = 5) -> list[PaperMetadata]:
        """Search papers by title."""

    def search_by_topic(self, topic: str, limit: int = 10) -> list[PaperMetadata]:
        """Search papers by free-text topic."""
