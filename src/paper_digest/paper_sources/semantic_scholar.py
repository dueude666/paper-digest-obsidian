"""Semantic Scholar source."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from paper_digest.config import AppSettings
from paper_digest.exceptions import SourceLookupError
from paper_digest.http import HttpClientProtocol
from paper_digest.models import PaperMetadata

LOGGER = logging.getLogger(__name__)


class SemanticScholarSource:
    """Semantic Scholar metadata source and hot-paper search client."""

    name = "semantic-scholar"

    CATEGORY_KEYWORDS = {
        "cs.AI": "artificial intelligence",
        "cs.LG": "machine learning",
        "cs.CL": "natural language processing",
        "cs.CV": "computer vision",
        "cs.MM": "multimedia",
        "cs.MA": "multi-agent systems",
        "cs.RO": "robotics",
    }

    def __init__(self, http_client: HttpClientProtocol, settings: AppSettings):
        self._http = http_client
        self._settings = settings

    def matches_url(self, url: str) -> bool:
        return "semanticscholar.org" in url

    def get_by_url(self, url: str) -> PaperMetadata:
        raise SourceLookupError("Semantic Scholar support is not implemented in this MVP.")

    def search_by_title(self, title: str, limit: int = 5) -> list[PaperMetadata]:
        payload = self._search(query=title, limit=limit)
        return [self._to_metadata(item) for item in payload if item.get("title")]

    def search_by_topic(self, topic: str, limit: int = 10) -> list[PaperMetadata]:
        payload = self._search(query=topic, limit=limit)
        return [self.to_metadata(item) for item in payload if item.get("title")]

    def search_hot_papers(
        self,
        *,
        categories: list[str],
        start_date: datetime,
        end_date: datetime,
        top_k_per_category: int = 5,
    ) -> list[dict[str, Any]]:
        papers: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for category in categories:
            query = self.CATEGORY_KEYWORDS.get(category, category)
            try:
                payload = self._search(
                    query=query,
                    limit=100,
                    publication_date_or_year=(
                        f"{start_date.strftime('%Y-%m-%d')}:{end_date.strftime('%Y-%m-%d')}"
                    ),
                )
            except Exception as error:
                LOGGER.warning(
                    "Skipping Semantic Scholar hot-paper search for category=%s: %s",
                    category,
                    error,
                )
                if "429" in str(error):
                    LOGGER.warning("Semantic Scholar rate limit encountered; stopping hot search.")
                    break
                time.sleep(self._settings.semantic_scholar_request_interval_seconds)
                continue
            ranked = sorted(
                payload,
                key=lambda item: int(item.get("influentialCitationCount") or 0),
                reverse=True,
            )
            for item in ranked[:top_k_per_category]:
                identifier = _semantic_identifier(item)
                if identifier in seen_ids:
                    continue
                seen_ids.add(identifier)
                item["source_kind"] = "hot"
                papers.append(item)
            time.sleep(self._settings.semantic_scholar_request_interval_seconds)

        return papers

    def to_metadata(self, item: dict[str, Any]) -> PaperMetadata:
        return self._to_metadata(item)

    def _search(
        self,
        *,
        query: str,
        limit: int,
        publication_date_or_year: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "fields": self._settings.semantic_scholar_fields,
        }
        if publication_date_or_year:
            params["publicationDateOrYear"] = publication_date_or_year
        payload = self._http.get_json(self._settings.semantic_scholar_api_url, params=params)
        data = payload.get("data", [])
        if not isinstance(data, list):
            LOGGER.warning("Unexpected Semantic Scholar response for query=%s", query)
            return []
        return [item for item in data if isinstance(item, dict)]

    def _to_metadata(self, item: dict[str, Any]) -> PaperMetadata:
        external_ids = item.get("externalIds") or {}
        arxiv_id = external_ids.get("ArXiv")
        paper_id = str(item.get("paperId") or arxiv_id or item.get("url") or item.get("title"))
        pdf_url = ""
        open_access_pdf = item.get("openAccessPdf")
        if isinstance(open_access_pdf, dict):
            pdf_url = str(open_access_pdf.get("url") or "")
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        abs_url = str(item.get("url") or "")
        if not abs_url and arxiv_id:
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"

        published_at = _parse_semantic_date(item.get("publicationDate"))
        return PaperMetadata(
            source=self.name,
            source_id=paper_id,
            arxiv_id=arxiv_id,
            title=str(item.get("title") or ""),
            authors=[
                str(author.get("name"))
                for author in item.get("authors", [])
                if isinstance(author, dict) and author.get("name")
            ],
            abstract=str(item.get("abstract") or ""),
            published_at=published_at,
            year=int(item["year"]) if item.get("year") else None,
            pdf_url=pdf_url,
            abs_url=abs_url,
            categories=[],
        )


def _parse_semantic_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _semantic_identifier(item: dict[str, Any]) -> str:
    external_ids = item.get("externalIds") or {}
    return str(external_ids.get("ArXiv") or item.get("paperId") or item.get("title") or "")
