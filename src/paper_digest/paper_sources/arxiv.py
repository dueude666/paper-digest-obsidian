"""arXiv metadata source."""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from paper_digest.config import AppSettings
from paper_digest.exceptions import SourceLookupError
from paper_digest.http import HttpClientProtocol
from paper_digest.models import PaperMetadata
from paper_digest.utils import extract_arxiv_id, normalize_whitespace, text_similarity

LOGGER = logging.getLogger(__name__)


class ArxivSource:
    """Metadata source backed by the arXiv Atom API."""

    name = "arxiv"

    def __init__(self, http_client: HttpClientProtocol, settings: AppSettings):
        self._http = http_client
        self._settings = settings

    def matches_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return "arxiv.org" in parsed.netloc

    def get_by_url(self, url: str) -> PaperMetadata:
        arxiv_id = extract_arxiv_id(url)
        if arxiv_id is None:
            raise SourceLookupError(f"Could not parse arXiv identifier from {url!r}.")
        results = self._query(id_list=arxiv_id, max_results=1)
        if not results:
            raise SourceLookupError(f"No arXiv result found for identifier {arxiv_id}.")
        return results[0]

    def search_by_title(self, title: str, limit: int = 5) -> list[PaperMetadata]:
        title = normalize_whitespace(title)
        query = f'ti:"{title.replace(chr(34), "")}"'
        results = self._query(search_query=query, max_results=max(limit * 2, 5))
        return sorted(results, key=lambda item: text_similarity(item.title, title), reverse=True)[
            :limit
        ]

    def search_by_topic(self, topic: str, limit: int = 10) -> list[PaperMetadata]:
        topic = normalize_whitespace(topic)
        exact_query = f'all:"{topic.replace(chr(34), "")}"'
        results = self._query(
            search_query=exact_query,
            max_results=limit,
            sort_by="submittedDate",
            sort_order="descending",
        )
        if len(results) >= limit or " " not in topic:
            return results[:limit]

        token_query = " AND ".join([f'all:"{token}"' for token in topic.split()])
        fallback_results = self._query(
            search_query=token_query,
            max_results=limit,
            sort_by="submittedDate",
            sort_order="descending",
        )
        combined = results + [
            item
            for item in fallback_results
            if item.source_id not in {r.source_id for r in results}
        ]
        return combined[:limit]

    def search_recent_by_categories(
        self,
        *,
        categories: list[str],
        start_date: datetime,
        end_date: datetime,
        max_results: int = 200,
    ) -> list[PaperMetadata]:
        category_query = " OR ".join(f"cat:{category}" for category in categories)
        date_query = (
            f"submittedDate:[{start_date.strftime('%Y%m%d')}0000 TO "
            f"{end_date.strftime('%Y%m%d')}2359]"
        )
        query = f"({category_query}) AND {date_query}"
        return self._query(
            search_query=query,
            max_results=max_results,
            sort_by="submittedDate",
            sort_order="descending",
        )

    def _query(
        self,
        *,
        search_query: str | None = None,
        id_list: str | None = None,
        max_results: int,
        sort_by: str = "relevance",
        sort_order: str = "descending",
    ) -> list[PaperMetadata]:
        params: dict[str, str | int] = {
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        if id_list is not None:
            params["id_list"] = id_list
        elif search_query is not None:
            params["search_query"] = search_query
        else:
            raise ValueError("Either search_query or id_list must be provided.")

        xml_text = self._http.get_text(self._settings.arxiv_api_url, params=params)
        return self._parse_feed(xml_text)

    def _parse_feed(self, xml_text: str) -> list[PaperMetadata]:
        soup = BeautifulSoup(xml_text, "xml")
        entries = soup.find_all("entry")
        parsed_entries: list[PaperMetadata] = []
        for entry in entries:
            parsed_entries.append(self._parse_entry(entry))
        return parsed_entries

    def _parse_entry(self, entry: BeautifulSoup) -> PaperMetadata:
        entry_id = normalize_whitespace(entry.find("id").text)
        title = normalize_whitespace(entry.find("title").text)
        abstract = normalize_whitespace(entry.find("summary").text)
        published_at = _parse_datetime(
            entry.find("published").text if entry.find("published") else None
        )
        updated_at = _parse_datetime(entry.find("updated").text if entry.find("updated") else None)
        authors = [
            normalize_whitespace(author.find("name").text) for author in entry.find_all("author")
        ]
        categories = [category.get("term", "").strip() for category in entry.find_all("category")]
        arxiv_id = extract_arxiv_id(entry_id)
        pdf_url = self._resolve_pdf_url(entry, arxiv_id=arxiv_id)
        comment = _read_prefixed_tag(entry, "comment")
        journal_ref = _read_prefixed_tag(entry, "journal_ref")
        doi = _read_prefixed_tag(entry, "doi")

        return PaperMetadata(
            source=self.name,
            source_id=arxiv_id or entry_id,
            arxiv_id=arxiv_id,
            title=title,
            authors=authors,
            abstract=abstract,
            published_at=published_at,
            updated_at=updated_at,
            pdf_url=pdf_url,
            abs_url=entry_id,
            categories=[category for category in categories if category],
            doi=doi,
            journal_ref=journal_ref,
            comment=comment,
        )

    @staticmethod
    def _resolve_pdf_url(entry: BeautifulSoup, *, arxiv_id: str | None) -> str:
        for link in entry.find_all("link"):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                href = link.get("href")
                if href:
                    return _normalize_pdf_url(href)
        if arxiv_id is None:
            raise SourceLookupError("Could not determine PDF URL for arXiv entry.")
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_prefixed_tag(entry: BeautifulSoup, name: str) -> str | None:
    tag = entry.find(f"arxiv:{name}") or entry.find(name)
    if tag is None or not tag.text:
        return None
    value = normalize_whitespace(tag.text)
    return value or None


def _normalize_pdf_url(url: str) -> str:
    parsed = urlparse(url)
    if "arxiv.org" not in parsed.netloc:
        return url
    if parsed.path.startswith("/pdf/") and not parsed.path.endswith(".pdf"):
        return f"{url}.pdf"
    return url
