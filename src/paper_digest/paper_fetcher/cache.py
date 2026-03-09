"""Local cache management."""

from __future__ import annotations

from pathlib import Path

from paper_digest.models import PaperMetadata, ParsedPaper
from paper_digest.utils import ensure_directory, file_safe_key


class CacheManager:
    """File-backed cache for metadata, PDFs, and parsed text."""

    def __init__(self, root: Path):
        self.root = root.expanduser()
        self.metadata_dir = ensure_directory(self.root / "metadata")
        self.pdf_dir = ensure_directory(self.root / "pdfs")
        self.parsed_dir = ensure_directory(self.root / "parsed")

    def metadata_path(self, source: str, source_id: str) -> Path:
        return ensure_directory(self.metadata_dir / source) / f"{file_safe_key(source_id)}.json"

    def pdf_path(self, metadata: PaperMetadata) -> Path:
        key = metadata.arxiv_id or metadata.source_id
        return ensure_directory(self.pdf_dir / metadata.source) / f"{file_safe_key(key)}.pdf"

    def parsed_path(self, metadata: PaperMetadata) -> Path:
        key = metadata.arxiv_id or metadata.source_id
        return ensure_directory(self.parsed_dir / metadata.source) / f"{file_safe_key(key)}.json"

    def load_metadata(self, source: str, source_id: str) -> PaperMetadata | None:
        path = self.metadata_path(source, source_id)
        if not path.exists():
            return None
        return PaperMetadata.model_validate_json(path.read_text(encoding="utf-8"))

    def save_metadata(self, metadata: PaperMetadata) -> Path:
        path = self.metadata_path(metadata.source, metadata.source_id)
        path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_parsed(self, metadata: PaperMetadata) -> ParsedPaper | None:
        path = self.parsed_path(metadata)
        if not path.exists():
            return None
        return ParsedPaper.model_validate_json(path.read_text(encoding="utf-8"))

    def save_parsed(self, parsed: ParsedPaper) -> Path:
        path = self.parsed_path(parsed.metadata)
        path.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
        return path
