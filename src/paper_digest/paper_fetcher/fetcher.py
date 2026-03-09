"""Fetcher orchestration for metadata lookup and PDF download."""

from __future__ import annotations

import logging
from pathlib import Path

from paper_digest.exceptions import DownloadError, SourceLookupError
from paper_digest.http import HttpClientProtocol
from paper_digest.models import PaperMetadata
from paper_digest.paper_fetcher.cache import CacheManager
from paper_digest.paper_sources.base import PaperSource
from paper_digest.utils import extract_arxiv_id

LOGGER = logging.getLogger(__name__)


class PaperFetcher:
    """Coordinate source lookup with local caching."""

    def __init__(
        self,
        *,
        sources: list[PaperSource],
        cache: CacheManager,
        http_client: HttpClientProtocol,
    ):
        self._sources = sources
        self._cache = cache
        self._http = http_client

    def fetch_by_url(self, url: str, force: bool = False) -> PaperMetadata:
        source = self._source_for_url(url)
        source_id = extract_arxiv_id(url) or url
        if not force:
            cached = self._cache.load_metadata(source.name, source_id)
            if cached is not None:
                LOGGER.debug("Loaded metadata from cache for %s", source_id)
                return cached

        metadata = source.get_by_url(url)
        self._cache.save_metadata(metadata)
        return metadata

    def search_title(self, title: str, limit: int = 5, force: bool = False) -> list[PaperMetadata]:
        source = self._primary_source()
        results = source.search_by_title(title=title, limit=limit)
        for metadata in results:
            if force or self._cache.load_metadata(metadata.source, metadata.source_id) is None:
                self._cache.save_metadata(metadata)
        return results

    def search_topic(self, topic: str, limit: int = 10, force: bool = False) -> list[PaperMetadata]:
        source = self._primary_source()
        results = source.search_by_topic(topic=topic, limit=limit)
        for metadata in results:
            if force or self._cache.load_metadata(metadata.source, metadata.source_id) is None:
                self._cache.save_metadata(metadata)
        return results

    def download_pdf(self, metadata: PaperMetadata, force: bool = False) -> Path:
        path = self._cache.pdf_path(metadata)
        if path.exists() and not force:
            LOGGER.debug("Using cached PDF %s", path)
            return path

        try:
            content = self._http.get_bytes(metadata.pdf_url)
        except Exception as error:
            raise DownloadError(f"Failed to download PDF for {metadata.title}: {error}") from error

        path.write_bytes(content)
        LOGGER.debug("Downloaded PDF to %s", path)
        return path

    def _source_for_url(self, url: str) -> PaperSource:
        for source in self._sources:
            if source.matches_url(url):
                return source
        raise SourceLookupError(f"No configured source can resolve URL: {url}")

    def _primary_source(self) -> PaperSource:
        if not self._sources:
            raise SourceLookupError("No paper sources are configured.")
        return self._sources[0]
