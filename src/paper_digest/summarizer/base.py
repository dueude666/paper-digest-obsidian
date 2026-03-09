"""Summarizer interfaces."""

from __future__ import annotations

from typing import Protocol

from paper_digest.models import PaperSummary, ParsedPaper, TopicSummary


class SummaryEngine(Protocol):
    """Contract implemented by summarization backends."""

    def summarize_paper(self, parsed_paper: ParsedPaper) -> PaperSummary:
        """Build a note-ready summary for a paper."""

    def summarize_topic(self, topic: str, query: str, papers: list[PaperSummary]) -> TopicSummary:
        """Build a multi-paper topic digest."""
