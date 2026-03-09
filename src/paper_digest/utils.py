"""Small utility helpers shared across modules."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path

ARXIV_ID_RE = re.compile(
    r"(?P<identifier>(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)",
    flags=re.IGNORECASE,
)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    text = normalize_whitespace(text)
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?。！？])\s+(?=[A-Z0-9\u4e00-\u9fff])", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def slugify(value: str, max_length: int = 80) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    buffer: list[str] = []
    for char in normalized:
        if _is_cjk(char):
            buffer.append(char)
            continue
        if char.isascii() and char.isalnum():
            buffer.append(char.lower())
            continue
        if char in "._-":
            buffer.append(char)
            continue
        buffer.append("-")
    slug = "".join(buffer).strip("-_.")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        return "untitled"
    return slug[:max_length].rstrip("-")


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_arxiv_id(value: str) -> str | None:
    match = ARXIV_ID_RE.search(value)
    if not match:
        return None
    return match.group("identifier")


def text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, normalize_whitespace(left).lower(), normalize_whitespace(right).lower()
    ).ratio()


def truncate_text(text: str, max_chars: int = 400) -> str:
    text = normalize_whitespace(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def file_safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-_.") or "item"


def format_authors(authors: list[str], max_authors: int = 3) -> str:
    if not authors:
        return "Unknown authors"
    if len(authors) <= max_authors:
        return ", ".join(authors)
    lead = ", ".join(authors[:max_authors])
    return f"{lead}, et al."


def _is_cjk(value: str) -> bool:
    codepoint = ord(value)
    return (
        0x4E00 <= codepoint <= 0x9FFF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0xF900 <= codepoint <= 0xFAFF
    )
