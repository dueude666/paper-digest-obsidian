"""Index and search existing Obsidian notes."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import yaml

from paper_digest.exceptions import NoteIndexError
from paper_digest.knowledge.common_words import COMMON_WORDS
from paper_digest.models import NoteIndex, NoteIndexEntry, NoteSearchResult
from paper_digest.utils import dedupe_preserve_order, extract_arxiv_id, normalize_whitespace

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)^---\s*\n?", re.DOTALL | re.MULTILINE)
IGNORED_TAG_KEYWORDS = {
    "arxiv",
    "daily",
    "index",
    "literature",
    "paper",
    "recommendation",
    "文献",
    "论文笔记",
    "专题索引",
    "每日推荐",
    "推荐清单",
}


class NoteIndexService:
    """Build a keyword index from existing markdown notes."""

    def build(self, *, vault_root: Path, include_root: Path | None = None) -> NoteIndex:
        if not vault_root.exists():
            raise NoteIndexError(f"Vault root not found: {vault_root}")

        scan_root = include_root or vault_root
        notes: list[NoteIndexEntry] = []
        keyword_index: dict[str, list[str]] = defaultdict(list)

        for note_path in sorted(scan_root.rglob("*.md")):
            if self._skip_path(note_path):
                continue
            entry = self._index_note(vault_root=vault_root, note_path=note_path)
            notes.append(entry)

            for keyword in dedupe_preserve_order(entry.title_keywords + entry.tag_keywords):
                lowered = keyword.lower()
                if lowered in COMMON_WORDS or len(lowered) < 2:
                    continue
                keyword_index[lowered].append(entry.path)

        return NoteIndex(
            notes=notes,
            keyword_to_notes={
                key: dedupe_preserve_order(value) for key, value in keyword_index.items()
            },
        )

    def search(
        self, *, note_index: NoteIndex, query: str, limit: int = 10
    ) -> list[NoteSearchResult]:
        tokens = [
            token.lower()
            for token in re.findall(
                r"[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9._+\-\u4e00-\u9fff]*", query
            )
            if len(token) >= 2
        ]
        if not tokens:
            return []

        results: list[NoteSearchResult] = []
        for note in note_index.notes:
            haystack = " ".join(
                [
                    note.title.lower(),
                    " ".join(note.authors).lower(),
                    " ".join(note.tags).lower(),
                    " ".join(note.title_keywords).lower(),
                    " ".join(note.tag_keywords).lower(),
                    (note.arxiv_id or "").lower(),
                ]
            )
            matched_terms = [token for token in tokens if token in haystack]
            if not matched_terms:
                continue

            score = 0.0
            for token in matched_terms:
                if token in note.title.lower():
                    score += 2.0
                elif token in " ".join(note.title_keywords).lower():
                    score += 1.5
                else:
                    score += 1.0
            results.append(
                NoteSearchResult(
                    path=note.path,
                    title=note.title,
                    score=score,
                    matched_terms=matched_terms,
                )
            )

        return sorted(results, key=lambda item: (-item.score, item.title.lower()))[:limit]

    @staticmethod
    def _skip_path(path: Path) -> bool:
        skip_parts = {
            ".git",
            ".obsidian",
            ".trash",
            ".cache",
            "assets",
            "图片素材",
            "论文配图",
        }
        return any(part.startswith(".") or part in skip_parts for part in path.parts)

    def _index_note(self, *, vault_root: Path, note_path: Path) -> NoteIndexEntry:
        content = note_path.read_text(encoding="utf-8")
        frontmatter = self._parse_frontmatter(content)
        title = str(frontmatter.get("title") or note_path.stem)
        tags = _normalize_tags(frontmatter.get("tags"))
        authors = [str(author) for author in frontmatter.get("authors", [])]
        arxiv_id = extract_arxiv_id(str(frontmatter.get("arxiv_id") or content or note_path.stem))
        title_keywords = _extract_title_keywords(title)
        tag_keywords = [tag for tag in tags if len(tag) >= 2 and _is_linkable_tag(tag)]
        return NoteIndexEntry(
            path=note_path.relative_to(vault_root).as_posix(),
            absolute_path=note_path,
            title=title,
            authors=authors,
            tags=tags,
            title_keywords=title_keywords,
            tag_keywords=tag_keywords,
            arxiv_id=arxiv_id,
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        match = FRONTMATTER_RE.match(content)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except Exception as error:
            raise NoteIndexError(f"Failed to parse note frontmatter: {error}") from error


def _extract_title_keywords(title: str) -> list[str]:
    keywords: list[str] = []
    normalized = normalize_whitespace(title)
    if not normalized:
        return []

    acronym_match = re.match(r"^([A-Z]{2,})(?:\s*:|\s+)", normalized)
    if acronym_match:
        keywords.append(acronym_match.group(1))

    before_colon = normalized.split(":", maxsplit=1)[0].strip()
    if 2 <= len(before_colon) <= 40:
        keywords.append(before_colon)

    chinese_phrases = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    keywords.extend(chinese_phrases)

    hyphen_terms = re.findall(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)+\b", normalized)
    keywords.extend(hyphen_terms)
    return dedupe_preserve_order(
        [keyword for keyword in keywords if keyword.lower() not in COMMON_WORDS]
    )


def _normalize_tags(raw_tags: object) -> list[str]:
    if raw_tags is None:
        return []
    values: list[str] = []
    if isinstance(raw_tags, list):
        for item in raw_tags:
            values.extend(_normalize_tags(item))
    elif isinstance(raw_tags, str):
        values.append(normalize_whitespace(raw_tags))
    return [value for value in dedupe_preserve_order(values) if value]


def _is_linkable_tag(tag: str) -> bool:
    lowered = tag.lower()
    return not (
        lowered in IGNORED_TAG_KEYWORDS
        or lowered.startswith("topic/")
        or lowered.startswith("arxiv/")
        or lowered.startswith("主题/")
    )
