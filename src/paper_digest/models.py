"""Pydantic data models shared across the project."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class PaperMetadata(BaseModel):
    """Metadata describing a paper."""

    model_config = ConfigDict(extra="ignore")

    source: str = "arxiv"
    source_id: str
    arxiv_id: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    published_at: datetime | None = None
    updated_at: datetime | None = None
    year: int | None = None
    pdf_url: str
    abs_url: str
    categories: list[str] = Field(default_factory=list)
    doi: str | None = None
    journal_ref: str | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def _populate_year(self) -> PaperMetadata:
        if self.year is None and self.published_at is not None:
            self.year = self.published_at.year
        return self


class PaperSection(BaseModel):
    """A parsed section from the paper body."""

    heading: str
    body: str
    order: int


class ParsedPaper(BaseModel):
    """Structured result of PDF extraction."""

    metadata: PaperMetadata
    pdf_path: Path | None = None
    text: str = ""
    abstract_text: str | None = None
    sections: list[PaperSection] = Field(default_factory=list)
    references_text: str | None = None
    extraction_method: Literal["pymupdf", "pdfplumber", "fallback-none"] = "fallback-none"
    warnings: list[str] = Field(default_factory=list)
    parsed_at: datetime = Field(default_factory=utc_now)

    @property
    def combined_abstract(self) -> str:
        if self.metadata.abstract.strip():
            return self.metadata.abstract
        return self.abstract_text or self.metadata.abstract

    @property
    def has_substantial_text(self) -> bool:
        return len(self.text.split()) >= 1200


class PaperSummary(BaseModel):
    """Structured note-ready paper summary."""

    metadata: PaperMetadata
    summary_basis: str
    one_sentence: str
    research_context: str = ""
    research_problem: str
    problem_evidence: str = ""
    core_method: str
    method_evidence: str = ""
    method_breakdown: list[str] = Field(default_factory=list)
    experiment_setup: list[str] = Field(default_factory=list)
    main_results: str
    results_evidence: str = ""
    key_findings: list[str] = Field(default_factory=list)
    figure_reading_tips: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    follow_up_advice: list[str] = Field(default_factory=list)
    reading_path: list[str] = Field(default_factory=list)
    citation: str
    short_overview: list[str] = Field(default_factory=list)
    problem_definition: str = ""
    method_category: str = ""
    datasets_or_benchmarks: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    paper_role: str = ""
    generated_at: datetime = Field(default_factory=utc_now)
    warnings: list[str] = Field(default_factory=list)


class TopicComparisonRow(BaseModel):
    """Row shown in the topic index comparison table."""

    title: str
    note_path: str
    problem_definition: str
    method_category: str
    datasets_or_benchmarks: str
    strengths: str
    limitations: str


class TopicSummary(BaseModel):
    """Multi-paper topic digest."""

    topic: str
    query: str
    limit: int
    selection_rationale: str
    why_these_papers: str
    overview: str
    papers: list[PaperSummary] = Field(default_factory=list)
    comparison_rows: list[TopicComparisonRow] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class WriteResult(BaseModel):
    """File write result returned by the writer layer."""

    path: Path
    relative_path: str
    content: str
    written: bool
    skipped: bool = False


class DoctorCheck(BaseModel):
    """Simple health-check result."""

    name: str
    ok: bool
    detail: str


class ResearchDomain(BaseModel):
    """One domain tracked by the daily recommender."""

    name: str
    keywords: list[str] = Field(default_factory=list)
    arxiv_categories: list[str] = Field(default_factory=list)
    priority: int = 1


class ResearchProfile(BaseModel):
    """Research interests used for recommendation scoring."""

    vault_path: Path | None = None
    research_domains: list[ResearchDomain] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)


class RecommendationScores(BaseModel):
    """Per-paper recommendation scores."""

    relevance: float
    recency: float
    popularity: float
    quality: float
    recommendation: float


class RecommendedPaper(BaseModel):
    """Scored paper candidate for daily recommendations."""

    metadata: PaperMetadata
    scores: RecommendationScores
    matched_domain: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    source_kind: Literal["recent", "hot"] = "recent"
    citation_count: int = 0
    influential_citation_count: int = 0
    existing_note_paths: list[str] = Field(default_factory=list)
    already_in_vault: bool = False
    generated_note_path: str | None = None


class DailyDigest(BaseModel):
    """Daily recommendation digest."""

    date: str
    profile_name: str
    selection_rationale: str
    overview: str
    recommended_papers: list[RecommendedPaper] = Field(default_factory=list)
    analyzed_papers: list[PaperSummary] = Field(default_factory=list)


class NoteIndexEntry(BaseModel):
    """One indexed Obsidian note."""

    path: str
    absolute_path: Path
    title: str
    authors: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    tag_keywords: list[str] = Field(default_factory=list)
    arxiv_id: str | None = None


class NoteIndex(BaseModel):
    """Keyword index built from existing Obsidian notes."""

    notes: list[NoteIndexEntry] = Field(default_factory=list)
    keyword_to_notes: dict[str, list[str]] = Field(default_factory=dict)


class NoteSearchResult(BaseModel):
    """Search result returned by note search."""

    path: str
    title: str
    score: float
    matched_terms: list[str] = Field(default_factory=list)


class ImageAsset(BaseModel):
    """One extracted image asset."""

    filename: str
    relative_path: str
    source: str
    ext: str
    size_bytes: int


class ImageExtractionResult(BaseModel):
    """Image extraction output for a paper."""

    assets: list[ImageAsset] = Field(default_factory=list)
    index_path: Path | None = None
