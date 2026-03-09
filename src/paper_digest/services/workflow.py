"""High-level paper processing workflow."""

from __future__ import annotations

import logging
from pathlib import Path

from paper_digest.config import AppSettings
from paper_digest.models import (
    ImageAsset,
    PaperFullView,
    PaperMetadata,
    PaperSummary,
    ParsedPaper,
    TopicSummary,
    WriteResult,
)
from paper_digest.obsidian_writer.writer import ObsidianWriter
from paper_digest.paper_fetcher.fetcher import PaperFetcher
from paper_digest.paper_images.extractor import PaperImageExtractor
from paper_digest.paper_parser.pdf_parser import PDFParser
from paper_digest.summarizer.base import SummaryEngine
from paper_digest.utils import extract_arxiv_id

LOGGER = logging.getLogger(__name__)


class PaperWorkflowService:
    """Coordinate lookup, parsing, summarization, and note writing."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        fetcher: PaperFetcher,
        parser: PDFParser,
        summarizer: SummaryEngine,
        writer: ObsidianWriter,
        image_extractor: PaperImageExtractor | None = None,
    ):
        self._settings = settings
        self._fetcher = fetcher
        self._parser = parser
        self._summarizer = summarizer
        self._writer = writer
        self._image_extractor = image_extractor

    def summarize_paper(
        self,
        *,
        url_or_id: str | None = None,
        title: str | None = None,
        topic: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        overwrite_strategy: str | None = None,
        vault_override: Path | None = None,
        note_index=None,
        extract_images: bool = False,
    ) -> tuple[PaperSummary, WriteResult]:
        metadata = self._resolve_single_metadata(url_or_id=url_or_id, title=title, force=force)
        return self.summarize_metadata(
            metadata=metadata,
            topic=topic or self._settings.default_topic,
            dry_run=dry_run,
            force=force,
            overwrite_strategy=overwrite_strategy,
            vault_override=vault_override,
            note_index=note_index,
            extract_images=extract_images,
        )

    def summarize_topic(
        self,
        *,
        query: str,
        limit: int,
        topic: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        overwrite_strategy: str | None = None,
        vault_override: Path | None = None,
        note_index=None,
        extract_images: bool = False,
    ) -> tuple[TopicSummary, list[WriteResult], WriteResult]:
        topic_name = topic or query
        metadatas = self._fetcher.search_topic(query, limit=limit, force=force)
        summaries: list[PaperSummary] = []
        note_results: list[WriteResult] = []

        for metadata in metadatas:
            summary, note_result = self.summarize_metadata(
                metadata=metadata,
                topic=topic_name,
                dry_run=dry_run,
                force=force,
                overwrite_strategy=overwrite_strategy,
                vault_override=vault_override,
                note_index=note_index,
                extract_images=extract_images,
            )
            summaries.append(summary)
            note_results.append(note_result)

        topic_summary = self._summarizer.summarize_topic(
            topic=topic_name,
            query=f"arXiv query={query!r}, limit={limit}",
            papers=summaries,
        )
        index_result = self._writer.write_topic_index(
            topic_summary=topic_summary,
            note_results=note_results,
            topic=topic_name,
            vault_override=vault_override,
            dry_run=dry_run,
            overwrite_strategy=overwrite_strategy,
            note_index=note_index,
        )
        return topic_summary, note_results, index_result

    def summarize_metadata(
        self,
        *,
        metadata: PaperMetadata,
        topic: str,
        dry_run: bool = False,
        force: bool = False,
        overwrite_strategy: str | None = None,
        vault_override: Path | None = None,
        note_index=None,
        extract_images: bool = False,
    ) -> tuple[PaperSummary, WriteResult]:
        summary, pdf_path = self._build_summary(metadata=metadata, force=force)
        image_assets: list[ImageAsset] = []
        if (
            extract_images
            and not dry_run
            and self._image_extractor is not None
            and pdf_path is not None
        ):
            topic_slug = self._writer.topic_slug(topic)
            paper_slug = self._writer.paper_slug(summary)
            topic_root = self._writer.topic_root(
                topic_slug=topic_slug,
                vault_override=vault_override,
                dry_run=dry_run,
            )
            extraction = self._image_extractor.extract(
                metadata=metadata,
                pdf_path=pdf_path,
                output_dir=topic_root / self._settings.assets_dir_name / paper_slug,
            )
            image_assets = extraction.assets

        note_result = self._writer.write_paper(
            summary=summary,
            topic=topic,
            vault_override=vault_override,
            dry_run=dry_run,
            overwrite_strategy=overwrite_strategy,
            note_index=note_index,
            image_assets=image_assets,
        )
        return summary, note_result

    def export_full_paper(
        self,
        *,
        url_or_id: str | None = None,
        title: str | None = None,
        topic: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        overwrite_strategy: str | None = None,
        vault_override: Path | None = None,
    ) -> tuple[PaperFullView, WriteResult]:
        metadata = self._resolve_single_metadata(url_or_id=url_or_id, title=title, force=force)
        parsed_paper, pdf_path = self._build_parsed_paper(metadata=metadata, force=force)
        resolved_topic = topic or self._settings.default_topic
        full_view = self._writer.build_full_view(
            parsed_paper=parsed_paper,
            topic=resolved_topic,
            pdf_source_path=pdf_path,
            vault_override=vault_override,
            dry_run=dry_run,
        )
        result = self._writer.write_full_paper(
            parsed_paper=parsed_paper,
            topic=resolved_topic,
            pdf_source_path=pdf_path,
            vault_override=vault_override,
            dry_run=dry_run,
            overwrite_strategy=overwrite_strategy,
        )
        return full_view, result

    def resolve_single_metadata(
        self,
        *,
        url_or_id: str | None = None,
        title: str | None = None,
        force: bool = False,
    ) -> PaperMetadata:
        return self._resolve_single_metadata(url_or_id=url_or_id, title=title, force=force)

    def build_summary(
        self,
        *,
        metadata: PaperMetadata,
        force: bool = False,
    ) -> tuple[PaperSummary, Path | None]:
        return self._build_summary(metadata=metadata, force=force)

    def build_parsed_paper(
        self,
        *,
        metadata: PaperMetadata,
        force: bool = False,
    ) -> tuple[ParsedPaper, Path | None]:
        return self._build_parsed_paper(metadata=metadata, force=force)

    def _resolve_single_metadata(
        self,
        *,
        url_or_id: str | None,
        title: str | None,
        force: bool,
    ) -> PaperMetadata:
        if title:
            candidates = self._fetcher.search_title(title=title, limit=5, force=force)
            if not candidates:
                raise ValueError(f"No paper found for title: {title}")
            return candidates[0]

        if not url_or_id:
            raise ValueError("Either url_or_id or title must be provided.")

        normalized = url_or_id
        if not url_or_id.startswith("http"):
            arxiv_id = extract_arxiv_id(url_or_id)
            if arxiv_id is not None:
                normalized = f"https://arxiv.org/abs/{arxiv_id}"
        return self._fetcher.fetch_by_url(normalized, force=force)

    def _build_summary(
        self, *, metadata: PaperMetadata, force: bool
    ) -> tuple[PaperSummary, Path | None]:
        parsed_paper, pdf_path = self._build_parsed_paper(metadata=metadata, force=force)
        return self._summarizer.summarize_paper(parsed_paper), pdf_path

    def _build_parsed_paper(
        self,
        *,
        metadata: PaperMetadata,
        force: bool,
    ) -> tuple[ParsedPaper, Path | None]:
        parsed_paper = ParsedPaper(metadata=metadata, abstract_text=metadata.abstract, warnings=[])
        pdf_path: Path | None = None
        try:
            pdf_path = self._fetcher.download_pdf(metadata=metadata, force=force)
        except Exception as error:
            LOGGER.warning("PDF download failed for %s: %s", metadata.title, error)
            parsed_paper.warnings.append(f"PDF download fallback: {error}")
            return parsed_paper, None

        try:
            parsed_paper = self._parser.parse(metadata=metadata, pdf_path=pdf_path, force=force)
        except Exception as error:
            LOGGER.warning(
                "Falling back to abstract-only parsing for %s: %s", metadata.title, error
            )
            parsed_paper = ParsedPaper(
                metadata=metadata,
                pdf_path=pdf_path,
                abstract_text=metadata.abstract,
                warnings=[f"PDF parsing fallback: {error}"],
            )
        return parsed_paper, pdf_path
