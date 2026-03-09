"""PDF parsing and section extraction."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from paper_digest.exceptions import ParseError
from paper_digest.models import PaperMetadata, PaperSection, ParsedPaper
from paper_digest.paper_fetcher.cache import CacheManager
from paper_digest.utils import normalize_whitespace, truncate_text

LOGGER = logging.getLogger(__name__)

SECTION_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+)?(?:[A-Z][A-Za-z0-9,&()/\-]{1,20}\s*){1,10}$"
)


class PDFParser:
    """Extract readable text from PDF files with a fallback strategy."""

    def __init__(self, cache: CacheManager | None = None):
        self._cache = cache

    def parse(self, metadata: PaperMetadata, pdf_path: Path, force: bool = False) -> ParsedPaper:
        if self._cache is not None and not force:
            cached = self._cache.load_parsed(metadata)
            if cached is not None and cached.pdf_path == pdf_path:
                LOGGER.debug("Loaded parsed text from cache for %s", metadata.source_id)
                return cached

        warnings: list[str] = []
        text = ""
        method = "fallback-none"

        try:
            text = self._extract_with_pymupdf(pdf_path)
            method = "pymupdf"
        except Exception as error:
            warnings.append(f"pymupdf extraction failed: {error}")
            LOGGER.warning("PyMuPDF extraction failed for %s: %s", pdf_path, error)

        if not text.strip():
            try:
                text = self._extract_with_pdfplumber(pdf_path)
                method = "pdfplumber"
            except Exception as error:
                warnings.append(f"pdfplumber extraction failed: {error}")
                LOGGER.warning("pdfplumber extraction failed for %s: %s", pdf_path, error)

        if not text.strip():
            warnings.append(
                "No extractable PDF body text found. Falling back to metadata abstract."
            )
            method = "fallback-none"

        normalized = self._normalize_pdf_text(text)
        sections = self._extract_sections(normalized)
        abstract_text = self._extract_abstract(normalized, sections) or metadata.abstract
        references_text = self._extract_references(normalized)

        parsed = ParsedPaper(
            metadata=metadata,
            pdf_path=pdf_path,
            text=normalized,
            abstract_text=abstract_text,
            sections=sections,
            references_text=references_text,
            extraction_method=method,
            warnings=warnings,
        )
        if self._cache is not None:
            self._cache.save_parsed(parsed)
        return parsed

    @staticmethod
    def _extract_with_pymupdf(pdf_path: Path) -> str:
        try:
            import fitz
        except ImportError as error:
            raise ParseError("PyMuPDF is not installed.") from error

        chunks: list[str] = []
        with fitz.open(pdf_path) as document:
            for page in document:
                page_text = page.get_text("text")
                if page_text:
                    chunks.append(page_text)
        return "\n\n".join(chunks)

    @staticmethod
    def _extract_with_pdfplumber(pdf_path: Path) -> str:
        try:
            import pdfplumber
        except ImportError as error:
            raise ParseError("pdfplumber is not installed.") from error

        chunks: list[str] = []
        with pdfplumber.open(pdf_path) as document:
            for page in document.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    chunks.append(page_text)
        return "\n\n".join(chunks)

    @staticmethod
    def _normalize_pdf_text(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"-\n(?=[a-z])", "", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _extract_sections(self, text: str) -> list[PaperSection]:
        if not text:
            return []

        lines = [line.strip() for line in text.splitlines()]
        sections: list[PaperSection] = []
        current_heading = "Body"
        current_body: list[str] = []

        def flush(order: int) -> None:
            body = normalize_whitespace("\n".join(current_body))
            if body:
                sections.append(PaperSection(heading=current_heading, body=body, order=order))

        order = 0
        for index, line in enumerate(lines):
            if not line:
                current_body.append("")
                continue
            if self._is_heading(line, index=index):
                flush(order)
                order += 1
                current_heading = line
                current_body = []
            else:
                current_body.append(line)

        flush(order)
        return sections

    @staticmethod
    def _is_heading(line: str, *, index: int) -> bool:
        if index < 3:
            return False
        if len(line) > 90 or len(line.split()) > 12:
            return False
        if line.endswith("."):
            return False
        lowered = line.lower().strip()
        if lowered in {"abstract", "references", "bibliography"}:
            return True
        return bool(SECTION_HEADING_RE.match(line))

    @staticmethod
    def _extract_abstract(text: str, sections: list[PaperSection]) -> str | None:
        for section in sections:
            if section.heading.lower().startswith("abstract") and section.body:
                return truncate_text(section.body, max_chars=2500)

        match = re.search(
            r"abstract\s+(?P<body>.+?)(?:\n(?:1\s+introduction|introduction|keywords)\b)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return truncate_text(normalize_whitespace(match.group("body")), max_chars=2500)
        return None

    @staticmethod
    def _extract_references(text: str) -> str | None:
        match = re.search(
            r"(?:^|\n)(references|bibliography)\s+(?P<body>.+)$",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        return truncate_text(normalize_whitespace(match.group("body")), max_chars=5000)
